import numpy as np

from face_watch.arcface_analyzer import ArcFaceAnalyzer


def test_arcface_blob_has_expected_shape_and_range():
    image = np.zeros((112, 112, 3), dtype=np.uint8)
    image[:, :, 0] = 255
    blob = ArcFaceAnalyzer._embedding_blob(image)
    assert blob.shape == (1, 3, 112, 112)
    assert blob.dtype == np.float32
    assert np.isclose(blob[0, 2, 0, 0], 1.0)
    assert np.isclose(blob[0, 0, 0, 0], -1.0)
