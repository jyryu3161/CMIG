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


def pca_embed(matrix: Any, *, n_components: int = 2) -> EmbedResult:
    """PCA 차원축소(5b). explained_variance_ratio 동반."""
    from sklearn.decomposition import PCA
    p = PCA(n_components=n_components, random_state=0)
    coords = p.fit_transform(matrix)
    return EmbedResult("pca", coords, [float(x) for x in p.explained_variance_ratio_])


def kmeans_cluster(matrix: Any, *, k: int) -> list[int]:
    """KMeans 클러스터링(5b) → 샘플별 라벨. random_state 고정(재현)."""
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, random_state=0, n_init=10)
    return [int(x) for x in km.fit_predict(matrix)]


def umap_embed(matrix: Any, *, n_components: int = 2, n_neighbors: int = 15) -> EmbedResult:
    """UMAP 비선형 임베딩(5c). random_state 고정(재현, 단 병렬성 저하 trade-off)."""
    import umap
    n = matrix.shape[0]
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=min(n_neighbors, max(2, n - 1)),
        random_state=0,
    )
    return EmbedResult("umap", reducer.fit_transform(matrix), None)
