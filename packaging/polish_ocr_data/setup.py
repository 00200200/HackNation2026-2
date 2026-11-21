import hashlib
import os
from http.client import HTTPException
from pathlib import Path
from urllib import request

UPSTREAM = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd"
MODEL_HASHES = {
    "pol.traineddata": "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2",
    "eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}


def read_model(filename, expected_digest):
    local_dir = os.environ.get("KIO_TESSDATA_SOURCE")
    source = Path(local_dir) / filename if local_dir else f"{UPSTREAM}/{filename}"
    try:
        if local_dir:
            data = source.read_bytes()
        else:
            with request.urlopen(source, timeout=30) as response:
                data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_digest:
            raise ValueError(f"SHA-256 is {digest}, expected {expected_digest}")
    except (OSError, HTTPException, ValueError) as error:
        raise RuntimeError(
            f"Could not load {filename} from {source}: {error}.\n"
            f"Copy both files into one folder:\n  {UPSTREAM}/pol.traineddata\n  {UPSTREAM}/eng.traineddata\n"
            "Set KIO_TESSDATA_SOURCE to its absolute path and rerun python -m pip install -r requirements.txt."
        ) from error
    return data


if __name__ == "__main__":
    from setuptools import setup
    from setuptools.command.install import install

    class InstallModels(install):
        def run(self):
            super().run()
            model_dir = Path(self.install_data) / "share/kio2json/tessdata"
            model_dir.mkdir(parents=True, exist_ok=True)
            for name, digest in MODEL_HASHES.items():
                (model_dir / name).write_bytes(read_model(name, digest))

    setup(cmdclass={"install": InstallModels})
