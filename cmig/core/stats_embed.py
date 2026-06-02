"""통계 5b/5c — 차원축소·클러스터링 (Roadmap Phase 3.8/3.9, §15).

Design Ref: §15 G5 / cmig-stats.design. Plan SC: SC-ST7~ST9.

sklearn(PCA·KMeans, 5b)·umap-learn(5c) 위임. 입력=조건×특징 행렬(예: sweep metric 매트릭스).
재현성: random_state 고정. 결과는 numpy ndarray(소비자가 tidy/그림으로 변환).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EmbedResult:
    method: str
    coords: Any                     # ndarray (n_samples, n_components)
    explained_variance: list[float] | None = None   # PCA 만


def _matrix_shape(matrix: Any) -> tuple[int, int]:
    shape = getattr(matrix, "shape", None)
    if shape is None or len(shape) != 2:
        raise ValueError("embedding input matrix must be 2-dimensional")
    n_samples, n_features = int(shape[0]), int(shape[1])
    if n_samples < 1 or n_features < 1:
        raise ValueError("embedding input matrix must have at least one sample and one feature")
    return n_samples, n_features


def pca_embed(matrix: Any, *, n_components: int = 2) -> EmbedResult:
    """PCA 차원축소(5b). explained_variance_ratio 동반."""
    from sklearn.decomposition import PCA
    n_samples, n_features = _matrix_shape(matrix)
    if n_components < 1 or n_components > min(n_samples, n_features):
        raise ValueError(
            "PCA n_components must be between 1 and min(n_samples, n_features)"
        )
    p = PCA(n_components=n_components, random_state=0)
    coords = p.fit_transform(matrix)
    return EmbedResult("pca", coords, [float(x) for x in p.explained_variance_ratio_])


def kmeans_cluster(matrix: Any, *, k: int) -> list[int]:
    """KMeans 클러스터링(5b) → 샘플별 라벨. random_state 고정(재현)."""
    from sklearn.cluster import KMeans
    n_samples, _ = _matrix_shape(matrix)
    if k < 1 or k > n_samples:
        raise ValueError("KMeans k must be between 1 and n_samples")
    km = KMeans(n_clusters=k, random_state=0, n_init=10)
    return [int(x) for x in km.fit_predict(matrix)]


def umap_embed(matrix: Any, *, n_components: int = 2, n_neighbors: int = 15) -> EmbedResult:
    """UMAP 비선형 임베딩(5c). random_state 고정(재현, 단 병렬성 저하 trade-off)."""
    import umap
    n, n_features = _matrix_shape(matrix)
    if n < 3:
        raise ValueError("UMAP requires at least 3 samples")
    if n_components < 1 or n_components > min(n - 2, n_features):
        raise ValueError("UMAP n_components must be between 1 and min(n_samples - 2, n_features)")
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=min(n_neighbors, max(2, n - 1)),
        random_state=0,
    )
    return EmbedResult("umap", reducer.fit_transform(matrix), None)
