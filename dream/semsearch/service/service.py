import abc
from typing import Callable, List
import uuid
import random
import math
from pathlib import Path

import numpy as np

import dream.voctree.api as vtapi
from dream import model


class Store(abc.ABC):
    def atomically(self, _: Callable[[any], None]) -> None:
        raise NotImplementedError("")

    def add_image_metadata(self, tx: any, im: model.Image) -> None:
        raise NotImplementedError("")

    def get_image_metadata(self, tx: any, im_id: uuid.UUID) -> model.Image:
        raise NotImplementedError("")


class ImageStore(abc.ABC):
    def store_matrix(self, _: model.Image) -> None:
        raise NotImplementedError("")

    def get_matrix(self, _: uuid.UUID) -> np.ndarray:
        raise NotImplementedError("")

    def get_im_path(self, im_id: uuid.UUID) -> Path:
        raise NotImplementedError("")


class CaptionFeatureExtractor(abc.ABC):
    def extract(self, caption: str) -> List[np.ndarray]:
        raise NotImplementedError("")


class ImageFeatureExtractor(abc.ABC):
    def extract(self, mat: np.ndarray) -> List[np.ndarray]:
        raise NotImplementedError("")


class SemSearchService:
    _N_NEAREST_CAPTIONS = 5

    _captions_vtree: vtapi.VocabularyTree
    _ims_vtree: vtapi.VocabularyTree
    _im_store: ImageStore
    _store: Store
    _caption_feature_extractor: CaptionFeatureExtractor
    _im_feature_extractor: ImageFeatureExtractor

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        captions_vtree: vtapi.VocabularyTree,
        ims_vtree: vtapi.VocabularyTree,
        im_store: ImageStore,
        store: Store,
        caption_feature_extractor: CaptionFeatureExtractor,
        im_feature_extractor: ImageFeatureExtractor,
    ) -> None:
        self._captions_vtree = captions_vtree
        self._ims_vtree = ims_vtree
        self._im_store = im_store
        self._store = store
        self._caption_feature_extractor = caption_feature_extractor
        self._im_feature_extractor = im_feature_extractor

    def seed_image(self, im: model.Image) -> None:
        self._im_store.store_matrix(im)

        # The code logic should always first search for image metadata in the db and then read the matrix.
        # Hence it is necessary to first write the matrix and then the metadata because they are operations
        # to different IO destinations.
        def _cb(tx: any) -> None:
            self._store.add_image_metadata(tx, im)

        self._store.atomically(_cb)

    def query_all_ims(self, caption: str, n: int) -> List[uuid.UUID]:
        nearest_doc_ids = self.query_labeled_ims(caption, self._N_NEAREST_CAPTIONS)

        query_im_doc = self._create_abstract_im(nearest_doc_ids)
        return self._ims_vtree.query(query_im_doc, n)

    def query_labeled_ims(self, caption: str, n: int) -> List[uuid.UUID]:
        caption_vecs = self._caption_feature_extractor.extract(caption)
        query_caption_doc = vtapi.Document(uuid.uuid4(), vectors=caption_vecs)

        return self._captions_vtree.query(query_caption_doc, n)

    def _create_abstract_im(self, nearest_doc_ids: List[uuid.UUID]) -> vtapi.Document:
        vecs = []
        total_vecs_count = 0

        for i, doc_id in enumerate(nearest_doc_ids):
            mat = self._im_store.get_matrix(doc_id)

            im_vecs = self._im_feature_extractor.extract(mat)
            total_vecs_count += len(im_vecs)

            # Uses the same principle as normalized discounted cumulative gain.
            sampled_im_vecs = random.sample(im_vecs, int(len(im_vecs) / math.log2(i + 2)))

            vecs += sampled_im_vecs

        sampled_vecs = random.sample(vecs, int(total_vecs_count / len(nearest_doc_ids)))

        return vtapi.Document(uuid.uuid4(), sampled_vecs)

    def get_im_path(self, im_id: uuid.UUID) -> Path:
        return self._im_store.get_im_path(im_id)

    def get_im_metadata(self, im_id: uuid.UUID) -> model.Image:
        im: model.Image = None

        def _cb(tx: any) -> None:
            nonlocal im
            im = self._store.get_image_metadata(tx, im_id)

        self._store.atomically(_cb)

        return im
