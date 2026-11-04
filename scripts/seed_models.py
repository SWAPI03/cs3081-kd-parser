"""Make sure s3://models/v1/ and v2/ exist. If a version is missing (fresh clone), download
model-<version>.tar.gz from the GitHub Release, verify it against models/<version>/model.sha256
from the repository, and upload the files. Exit status 1 if v1 is still missing."""
import hashlib
import io
import os
import sys
import tarfile
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "worker"))
import s3util  # noqa: E402


def conf():
    values = {}
    for line in open(os.path.join(ROOT, "scripts", "release.conf"), encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            values[k] = v
    return values


def main():
    os.chdir(ROOT)
    s3 = s3util.client()
    c = conf()
    have = {}
    for version in ("v1", "v2"):
        if s3util.list_keys(s3, "models", f"{version}/config.json"):
            print(f"s3://models/{version}/ present")
            have[version] = True
            continue
        sha_file = f"models/{version}/model.sha256"
        if not os.path.exists(sha_file) or "REPLACE" in c["GITHUB_REPO"]:
            print(f"s3://models/{version}/ missing and no Release configured")
            have[version] = False
            continue
        expected = open(sha_file).read().split()[0]
        url = (f"https://github.com/{c['GITHUB_REPO']}/releases/download/"
               f"{c['RELEASE_TAG']}/model-{version}.tar.gz")
        print(f"downloading {url}")
        data = urllib.request.urlopen(url, timeout=300).read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            sys.exit(f"checksum mismatch for {url}: {digest} != {expected}")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                s3util.put_bytes(s3, "models", f"{version}/{member.name}", tar.extractfile(member).read())
        s3util.put_bytes(s3, "models", f"{version}/model.sha256", open(sha_file, "rb").read())
        print(f"s3://models/{version}/ seeded from the Release (sha256 verified)")
        have[version] = True
    sys.exit(0 if have.get("v1") else 1)


if __name__ == "__main__":
    main()
