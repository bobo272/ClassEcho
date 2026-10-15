import hashlib
import io
import json

import pytest

from backend.app import model_download


@pytest.mark.parametrize("mode", ["valid", "wrong-range", "wrong-hash"])
def test_range_download_verifies_metadata_and_content(tmp_path, monkeypatch, mode):
    data = b"model-weights-for-testing"
    metadata = {
        "sha": "pinned-revision",
        "siblings": [
            {
                "rfilename": "weights.npz",
                "lfs": {
                    "size": len(data),
                    "sha256": hashlib.sha256(
                        data if mode != "wrong-hash" else b"wrong"
                    ).hexdigest(),
                },
            }
        ],
    }

    class Response(io.BytesIO):
        status = 206
        headers = {
            "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}"
            if mode != "wrong-range"
            else "bytes 1-2/3"
        }

    def open_url(url, timeout):
        if isinstance(url, str):
            return io.BytesIO(json.dumps(metadata).encode())
        assert url.headers["Range"] == f"bytes=0-{len(data) - 1}"
        return Response(data)

    monkeypatch.setattr(model_download.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(model_download.time, "sleep", lambda _: None)
    if mode == "valid":
        model_download.download_ranges("test/model", "pinned-revision", tmp_path)
        assert (tmp_path / "weights.npz").read_bytes() == data
    else:
        with pytest.raises(ValueError):
            model_download.download_ranges("test/model", "pinned-revision", tmp_path)
        assert not (tmp_path / "weights.npz").exists()
