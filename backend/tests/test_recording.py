import subprocess

from backend.app.media import media_dir


def test_browser_webm_without_duration_is_imported(client, tmp_path, wav_bytes):
    source, target = tmp_path / "input.wav", tmp_path / "capture.webm"
    source.write_bytes(wav_bytes)
    # Non-seekable output reproduces a browser recording without a duration header.
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(source), "-c:a", "libopus", "-f", "webm", "pipe:1"],
        check=True,
        capture_output=True,
    )
    target.write_bytes(result.stdout)
    course = client.post("/api/courses", json={"name": "录音测试"}).json()
    response = client.post(
        f"/api/courses/{course['id']}/lectures",
        files={"file": ("课堂录音.webm", target.read_bytes(), "audio/webm")},
    )
    assert response.status_code == 201
    lecture = response.json()
    assert abs(lecture["duration"] - 2) < 0.1
    assert (media_dir(lecture["id"]) / "original.webm").is_file()
    assert (media_dir(lecture["id"]) / "normalized.wav").is_file()
