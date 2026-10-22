"""
知识库服务 — 文档向量化 + 语义检索（基于 FAISS + fastembed）

架构：
- 文档切分 → fastembed 生成向量（本地，无需 API）→ 构建 FAISS 索引
- FAISS 索引文件 + JSON 元数据文件存储在 data/ 目录下
- 检索时：问题向量化 → FAISS 搜索 → 返回元数据

零外部 API 依赖，纯本地运行。
"""

import json
import logging
import os
import re
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 全局锁（线程安全重建索引） ──
_index_lock = threading.Lock()

# ── 数据目录（避免中文路径，FAISS Windows 不兼容 Unicode） ──
_DEFAULT_DATA_DIR = "/ai_knowledge_data" if os.name != "nt" else "C:/ai_knowledge_data"
_DATA_DIR = Path(os.environ.get("KNOWLEDGE_DATA_DIR", _DEFAULT_DATA_DIR))
_INDEX_FILE = _DATA_DIR / "knowledge.index"
_META_FILE = _DATA_DIR / "knowledge_meta.json"

# ── Embedding 模型（全局单例） ──
_EMBEDDING_MODEL = None
_EMBEDDING_DIM = 512  # bge-small-zh-v1.5 输出维度


def _get_embedding_model():
    """懒加载 fastembed 模型（使用国内镜像）"""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        import os
        # HuggingFace 国内镜像（解决连接超时）
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from fastembed import TextEmbedding
        logger.info("🔄 加载 embedding 模型（首次会下载，约 30MB）...")
        _EMBEDDING_MODEL = TextEmbedding(
            model_name="BAAI/bge-small-zh-v1.5",
            max_length=512,
        )
        logger.info("✅ Embedding 模型加载完成")
    return _EMBEDDING_MODEL


# ════════════════════════════════════════════════════════════════
# 1. 文档发现
# ════════════════════════════════════════════════════════════════

def _find_docs_dir() -> Path | None:
    """定位 docs 目录（适配本地和 Docker 不同部署层级）。"""
    this_file = Path(__file__).resolve()

    def _try(expr):
        try:
            return expr()
        except (IndexError, OSError):
            return None

    seen = set()
    for candidate in [
        lambda: this_file.parents[4] / "docs",
        lambda: this_file.parents[3] / "docs",
        lambda: this_file.parents[2] / "docs",
        lambda: this_file.parents[1] / "docs",
        lambda: Path("/app/docs"),
    ]:
        p = _try(candidate)
        if p is not None:
            try:
                resolved = p.resolve()
                if resolved.exists() and str(resolved) not in seen:
                    seen.add(str(resolved))
                    if (resolved / "功能模块").exists() or list(resolved.glob("**/*.md")):
                        return resolved
            except (OSError, IndexError):
                continue

    # 最后兜底
    docker_docs = Path("/app/docs")
    if docker_docs.exists():
        return docker_docs
    return None


def _discover_md_files(docs_dir: Path) -> list[Path]:
    """扫描 docs_dir 下需要纳入知识库的 .md 文件"""
    func_dir = docs_dir / "功能模块"
    if not func_dir.exists():
        logger.warning("功能模块/ 目录不存在，回退扫描全部 .md")
        return sorted(docs_dir.glob("**/*.md"))
    return sorted(func_dir.rglob("*.md"))


# ════════════════════════════════════════════════════════════════
# 2. 文档切分
# ════════════════════════════════════════════════════════════════

def _chunk_markdown(content: str, doc_title: str, doc_group: str) -> list[dict]:
    """按 ## 二级标题将 .md 文件切成语义块"""
    lines = content.split("\n")
    chunks = []
    current_heading = "概述"
    current_lines: list[str] = []
    chunk_index = 0

    for line in lines:
        if re.match(r"^##\s+", line) and not re.match(r"^###\s+", line):
            text = _finalize_chunk(current_lines)
            if text:
                chunks.append({
                    "content": text,
                    "doc_title": doc_title,
                    "doc_group": doc_group,
                    "heading": current_heading,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1
            current_heading = re.sub(r"^##\s+", "", line).strip()
            current_lines = []
        else:
            if re.match(r"^#\s", line) or re.match(r"^---+$", line):
                continue
            current_lines.append(line)

    text = _finalize_chunk(current_lines)
    if text:
        chunks.append({
            "content": text,
            "doc_title": doc_title,
            "doc_group": doc_group,
            "heading": current_heading,
            "chunk_index": chunk_index,
        })
    return chunks


def _finalize_chunk(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ════════════════════════════════════════════════════════════════
# 3. 向量嵌入（本地 fastembed，无需 API）
# ════════════════════════════════════════════════════════════════

def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """批量生成向量，返回 list[list[float]]"""
    model = _get_embedding_model()
    # fastembed 返回 generator of numpy.ndarray
    results = list(model.embed(texts))
    return [r.tolist() for r in results]


def _get_embedding(text: str) -> list[float]:
    """生成单个文本的向量"""
    return _get_embeddings([text])[0]


# ════════════════════════════════════════════════════════════════
# 4. 知识库构建 + FAISS 索引
# ════════════════════════════════════════════════════════════════

def rebuild_knowledge_base() -> int:
    """
    扫描文档 → 切分 → 生成向量 → 构建 FAISS 索引 → 保存到文件。
    返回写入的 chunk 总数。
    """
    docs_dir = _find_docs_dir()
    if docs_dir is None:
        logger.error("无法定位 docs 目录，知识库重建失败")
        return 0

    logger.info(f"📂 文档目录: {docs_dir}")

    md_files = _discover_md_files(docs_dir)
    if not md_files:
        logger.warning("未找到 .md 文档")
        return 0

    logger.info(f"📄 发现 {len(md_files)} 个文档")

    # 切分
    all_chunks: list[dict] = []
    for fp in md_files:
        try:
            text = fp.read_text(encoding="utf-8")
            rel = fp.relative_to(docs_dir)
            doc_group = rel.parts[0] if len(rel.parts) > 1 else "未分组"
            doc_title = fp.stem
            doc_title_clean = re.sub(r"^\d+_", "", doc_title)
            chunks = _chunk_markdown(text, doc_title_clean, doc_group)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"读取/切分失败 [{fp.name}]: {e}")

    logger.info(f"✂️ 切分完成：{len(all_chunks)} 个 chunk")

    if not all_chunks:
        return 0

    # 生成向量
    texts = [c["content"] for c in all_chunks]
    logger.info(f"🔄 开始生成 Embeddings（共 {len(texts)} 条，本地模型）...")
    embeddings = _get_embeddings(texts)
    logger.info("✅ Embeddings 生成完成")

    # 构建 FAISS 索引（余弦相似度）
    import numpy as np
    import faiss

    dim = len(embeddings[0])
    emb_array = np.array(embeddings).astype("float32")

    # 归一化后内积 = 余弦相似度
    faiss.normalize_L2(emb_array)

    index = faiss.IndexFlatIP(dim)
    index.add(emb_array)

    # 确保 data 目录
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _index_lock:
        faiss.write_index(index, str(_INDEX_FILE))
        meta = {"chunks": all_chunks}
        _META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"💾 知识库重建完成：{len(all_chunks)} 条记录")
    logger.info(f"   FAISS 索引: {_INDEX_FILE}")
    logger.info(f"   元数据文件: {_META_FILE}")

    return len(all_chunks)


# ════════════════════════════════════════════════════════════════
# 5. 语义检索
# ════════════════════════════════════════════════════════════════

def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """
    语义检索：对用户问题做向量搜索，返回最相关的 chunk 列表。
    不需要 db 参数——FAISS 是文件存储。
    """
    if not query.strip():
        return []

    import numpy as np
    import faiss

    if not _INDEX_FILE.exists() or not _META_FILE.exists():
        logger.warning("知识库索引不存在，请先重建")
        return []

    try:
        with _index_lock:
            index = faiss.read_index(str(_INDEX_FILE))
            meta = json.loads(_META_FILE.read_text(encoding="utf-8"))

        chunks = meta["chunks"]
        if not chunks:
            return []

        # 生成查询向量
        query_emb = _get_embedding(query)
        query_array = np.array([query_emb]).astype("float32")
        faiss.normalize_L2(query_array)

        k = min(top_k, index.ntotal)
        if k == 0:
            return []

        scores, indices = index.search(query_array, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(chunks):
                continue
            chunk = chunks[idx]
            results.append({
                "content": chunk["content"],
                "doc_title": chunk["doc_title"],
                "doc_group": chunk["doc_group"],
                "heading": chunk["heading"],
                "chunk_index": chunk["chunk_index"],
                "similarity": round(float(score), 4),
            })

        return results

    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        return []


# ════════════════════════════════════════════════════════════════
# 6. 状态查询
# ════════════════════════════════════════════════════════════════

def get_knowledge_status() -> dict:
    """获取知识库状态"""
    if not _INDEX_FILE.exists() or not _META_FILE.exists():
        return {"status": "empty", "count": 0, "doc_count": 0, "groups": []}

    try:
        meta = json.loads(_META_FILE.read_text(encoding="utf-8"))
        chunks = meta["chunks"]
        doc_titles = set(c["doc_title"] for c in chunks)
        groups = list(set(c["doc_group"] for c in chunks))
        return {
            "status": "ready",
            "count": len(chunks),
            "doc_count": len(doc_titles),
            "groups": sorted(groups),
        }
    except Exception as e:
        logger.warning(f"读取知识库元数据失败: {e}")
        return {"status": "error", "count": 0, "doc_count": 0, "groups": []}
