from typing import List
import logging

import psycopg

from dream import model


def sample_im_metadata(pg_tx: psycopg.Cursor, sample_size: int) -> List[model.Image]:
    im_count = _get_im_count(pg_tx)

    if im_count < sample_size:
        logging.warn(
            f"sample_size ({sample_size}) is greater than training dataset size ({im_count}), setting to 100%",
        )
        sample_size = im_count

    if sample_size / im_count < 1:
        logging.warn(f"sample_size must be >= 1% of the total number of images, setting it to 1%")
        sample_size = im_count / 100 + 1

    return _load_im_metadata(pg_tx, sample_size, im_count)


def _get_im_count(pg_tx: psycopg.Cursor) -> int:
    pg_tx.execute("SELECT COUNT(*) FROM image_metadata;")
    row = pg_tx.fetchone()
    return row[0]


def _load_im_metadata(pg_tx: psycopg.Cursor, sample_size: int, im_count: int) -> List[model.Image]:
    pg_tx.execute(
        f"SELECT id, labels, dataset FROM image_metadata TABLESAMPLE BERNOULLI (({sample_size}*100/{im_count}));",
    )
    ims = []

    for row in pg_tx.fetchall():
        im = model.Image().with_id(model.ImageID(row[0])).with_dataset(row[2]).with_captions(row[1])
        ims.append(im)

    return ims
