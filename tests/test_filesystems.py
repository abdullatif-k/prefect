import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple

import pytest

import prefect
from prefect.exceptions import InvalidRepositoryURLError
from prefect.filesystems import GitHub, LocalFileSystem, RemoteFileSystem
from prefect.testing.utilities import AsyncMock

TEST_PROJECTS_DIR = prefect.__root_path__ / "tests" / "test-projects"


def setup_test_directory(tmp_src: str, sub_dir: str = "puppy") -> Tuple[str, str]:
    """Add files and directories to a temporary directory. Returns a tuple with the
    expected parent-level contents and the expected child-level contents.
    """
    # add file to tmp_src
    f1_name = "dog.text"
    f1_path = Path(tmp_src) / f1_name
    f1 = open(f1_path, "w")
    f1.close()

    # add sub-directory to tmp_src
    sub_dir_path = Path(tmp_src) / sub_dir
    os.mkdir(sub_dir_path)

    # add file to sub-directory
    f2_name = "cat.txt"
    f2_path = sub_dir_path / f2_name
    f2 = open(f2_path, "w")
    f2.close()

    parent_contents = {f1_name, sub_dir}
    child_contents = {f2_name}

    assert set(os.listdir(tmp_src)) == parent_contents
    assert set(os.listdir(sub_dir_path)) == child_contents

    return parent_contents, child_contents


class TestLocalFileSystem:
    async def test_read_write_roundtrip(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path))
        await fs.write_path("test.txt", content=b"hello")
        assert await fs.read_path("test.txt") == b"hello"

    def test_read_write_roundtrip_sync(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path))
        fs.write_path("test.txt", content=b"hello")
        assert fs.read_path("test.txt") == b"hello"

    async def test_write_with_missing_directory_creates(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path))
        await fs.write_path(Path("folder") / "test.txt", content=b"hello")
        assert (tmp_path / "folder").exists()
        assert (tmp_path / "folder" / "test.txt").read_text() == "hello"

    async def test_write_outside_of_basepath(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path / "foo"))
        with pytest.raises(ValueError, match="..."):
            await fs.write_path(tmp_path / "bar" / "test.txt", content=b"hello")

    async def test_read_fails_for_directory(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path))
        (tmp_path / "folder").mkdir()
        with pytest.raises(ValueError, match="not a file"):
            await fs.read_path(tmp_path / "folder")

    async def test_resolve_path(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path))

        assert fs._resolve_path(tmp_path) == tmp_path
        assert fs._resolve_path(tmp_path / "subdirectory") == tmp_path / "subdirectory"
        assert fs._resolve_path("subdirectory") == tmp_path / "subdirectory"

    async def test_get_directory_duplicate_directory(self, tmp_path):
        fs = LocalFileSystem(basepath=str(tmp_path))
        await fs.get_directory(".", ".")

    async def test_dir_contents_copied_correctly_with_get_directory(self):

        sub_dir_name = "puppy"

        with TemporaryDirectory() as tmp_src:
            parent_contents, child_contents = setup_test_directory(
                tmp_src, sub_dir_name
            )
            # move file contents to tmp_dst
            with TemporaryDirectory() as tmp_dst:

                f = LocalFileSystem()

                await f.get_directory(from_path=tmp_src, local_path=tmp_dst)
                assert set(os.listdir(tmp_dst)) == set(parent_contents)
                assert set(os.listdir(Path(tmp_dst) / sub_dir_name)) == set(
                    child_contents
                )

    async def test_dir_contents_copied_correctly_with_put_directory(self):

        sub_dir_name = "puppy"

        with TemporaryDirectory() as tmp_src:
            parent_contents, child_contents = setup_test_directory(
                tmp_src, sub_dir_name
            )
            # move file contents to tmp_dst
            with TemporaryDirectory() as tmp_dst:

                f = LocalFileSystem()

                await f.put_directory(
                    local_path=tmp_src,
                    to_path=tmp_dst,
                )

                assert set(os.listdir(tmp_dst)) == set(parent_contents)
                assert set(os.listdir(Path(tmp_dst) / sub_dir_name)) == set(
                    child_contents
                )

    async def test_dir_contents_copied_correctly_with_put_directory_and_file_pattern(
        self,
    ):
        """Make sure that ignore file behaves properly."""

        sub_dir_name = "puppy"

        with TemporaryDirectory() as tmp_src:
            parent_contents, child_contents = setup_test_directory(
                tmp_src, sub_dir_name
            )

            # ignore .py files
            ignore_fpath = Path(tmp_src) / ".ignore"
            with open(ignore_fpath, "w") as f:
                f.write("*.py")

            # contents without .py files
            expected_contents = os.listdir(tmp_src)

            # add .py files
            with open(Path(tmp_src) / "dog.py", "w") as f:
                f.write("pass")

            with open(Path(tmp_src) / sub_dir_name / "cat.py", "w") as f:
                f.write("pass")

            # move file contents to tmp_dst
            with TemporaryDirectory() as tmp_dst:

                f = LocalFileSystem()

                await f.put_directory(
                    local_path=tmp_src, to_path=tmp_dst, ignore_file=ignore_fpath
                )
                assert set(os.listdir(tmp_dst)) == set(expected_contents)
                assert set(os.listdir(Path(tmp_dst) / sub_dir_name)) == set(
                    child_contents
                )

    async def test_dir_contents_copied_correctly_with_put_directory_and_directory_pattern(
        self,
    ):
        """Make sure that ignore file behaves properly."""

        sub_dir_name = "puppy"
        skip_sub_dir = "kitty"

        with TemporaryDirectory() as tmp_src:
            parent_contents, child_contents = setup_test_directory(
                tmp_src, sub_dir_name
            )

            # ignore .py files
            ignore_fpath = Path(tmp_src) / ".ignore"
            with open(ignore_fpath, "w") as f:
                f.write(f"**/{skip_sub_dir}/*")

            skip_sub_dir_path = Path(tmp_src) / skip_sub_dir
            os.mkdir(skip_sub_dir_path)

            # add file to sub-directory
            f2_name = "kitty-cat.txt"
            f2_path = skip_sub_dir_path / f2_name
            f2 = open(f2_path, "w")
            f2.close()

            expected_parent_contents = os.listdir(tmp_src)
            # move file contents to tmp_dst
            with TemporaryDirectory() as tmp_dst:

                f = LocalFileSystem()

                await f.put_directory(
                    local_path=tmp_src, to_path=tmp_dst, ignore_file=ignore_fpath
                )
                assert set(os.listdir(tmp_dst)) == set(expected_parent_contents)
                assert set(os.listdir(Path(tmp_dst) / sub_dir_name)) == set(
                    child_contents
                )


class TestRemoteFileSystem:
    def test_must_contain_scheme(self):
        with pytest.raises(ValueError, match="must start with a scheme"):
            RemoteFileSystem(basepath="foo")

    def test_must_contain_net_location(self):
        with pytest.raises(
            ValueError, match="must include a location after the scheme"
        ):
            RemoteFileSystem(basepath="memory://")

    async def test_read_write_roundtrip(self):
        fs = RemoteFileSystem(basepath="memory://root")
        await fs.write_path("test.txt", content=b"hello")
        assert await fs.read_path("test.txt") == b"hello"

    def test_read_write_roundtrip_sync(self):
        fs = RemoteFileSystem(basepath="memory://root")
        fs.write_path("test.txt", content=b"hello")
        assert fs.read_path("test.txt") == b"hello"

    async def test_write_with_missing_directory_succeeds(self):
        fs = RemoteFileSystem(basepath="memory://root/")
        await fs.write_path("memory://root/folder/test.txt", content=b"hello")
        assert await fs.read_path("folder/test.txt") == b"hello"

    async def test_write_outside_of_basepath_netloc(self):
        fs = RemoteFileSystem(basepath="memory://foo")
        with pytest.raises(ValueError, match="is outside of the base path"):
            await fs.write_path("memory://bar/test.txt", content=b"hello")

    async def test_write_outside_of_basepath_subpath(self):
        fs = RemoteFileSystem(basepath="memory://root/foo")
        with pytest.raises(ValueError, match="is outside of the base path"):
            await fs.write_path("memory://root/bar/test.txt", content=b"hello")

    async def test_write_to_different_scheme(self):
        fs = RemoteFileSystem(basepath="memory://foo")
        with pytest.raises(
            ValueError,
            match="with scheme 'file' must use the same scheme as the base path 'memory'",
        ):
            await fs.write_path("file://foo/test.txt", content=b"hello")

    async def test_read_fails_does_not_exist(self):
        fs = RemoteFileSystem(basepath="memory://root")
        with pytest.raises(FileNotFoundError):
            await fs.read_path("foo/bar")

    async def test_resolve_path(self):
        base = "memory://root"
        fs = RemoteFileSystem(basepath=base)

        assert fs._resolve_path(base) == base + "/"
        assert fs._resolve_path(f"{base}/subdir") == f"{base}/subdir"
        assert fs._resolve_path("subdirectory") == f"{base}/subdirectory"

    async def test_put_directory_flat(self):
        fs = RemoteFileSystem(basepath="memory://flat")
        await fs.put_directory(
            os.path.join(TEST_PROJECTS_DIR, "flat-project"),
            ignore_file=os.path.join(
                TEST_PROJECTS_DIR, "flat-project", ".prefectignore"
            ),
        )
        copied_files = set(fs.filesystem.glob("/flat/**"))

        assert copied_files == {
            "/flat/explicit_relative.py",
            "/flat/implicit_relative.py",
            "/flat/shared_libs.py",
        }

    async def test_put_directory_tree(self):
        fs = RemoteFileSystem(basepath="memory://tree")
        await fs.put_directory(
            os.path.join(TEST_PROJECTS_DIR, "tree-project"),
            ignore_file=os.path.join(
                TEST_PROJECTS_DIR, "tree-project", ".prefectignore"
            ),
        )
        copied_files = set(fs.filesystem.glob("/tree/**"))

        assert copied_files == {
            "/tree/imports",
            "/tree/imports/explicit_relative.py",
            "/tree/imports/implicit_relative.py",
            "/tree/shared_libs",
            "/tree/shared_libs/bar.py",
            "/tree/shared_libs/foo.py",
            "/tree/.hidden",
        }

    async def test_put_directory_put_file_count(self):
        ignore_file = os.path.join(TEST_PROJECTS_DIR, "tree-project", ".prefectignore")

        # Put files
        fs = RemoteFileSystem(basepath="memory://tree")
        num_files_put = await fs.put_directory(
            os.path.join(TEST_PROJECTS_DIR, "tree-project"),
            ignore_file=ignore_file,
        )

        # Expected files
        ignore_patterns = Path(ignore_file).read_text().splitlines(keepends=False)
        included_files = prefect.utilities.filesystem.filter_files(
            os.path.join(TEST_PROJECTS_DIR, "tree-project"),
            ignore_patterns,
            include_dirs=False,
        )
        num_files_expected = len(included_files)

        assert num_files_put == num_files_expected


class TestGitHub:
    class MockTmpDir:
        """Utility for having `TemporaryDirectory` return a known location."""

        dir = None

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self.dir

        def __exit__(self, *args, **kwargs):
            pass

    async def test_subprocess_errors_are_surfaced(self):
        g = GitHub(repository="incorrect-url-scheme")
        with pytest.raises(
            OSError, match="fatal: repository 'incorrect-url-scheme' does not exist"
        ):
            await g.get_directory()

    async def test_repository_default(self, monkeypatch):
        class p:
            returncode = 0

        mock = AsyncMock(return_value=p())
        monkeypatch.setattr(prefect.filesystems, "run_process", mock)
        g = GitHub(repository="prefect")
        await g.get_directory()

        assert mock.await_count == 1
        expected_cmd = ["git", "clone", "prefect"]
        assert mock.await_args[0][0][: len(expected_cmd)] == expected_cmd

    async def test_reference_default(self, monkeypatch):
        class p:
            returncode = 0

        mock = AsyncMock(return_value=p())
        monkeypatch.setattr(prefect.filesystems, "run_process", mock)
        g = GitHub(repository="prefect", reference="2.0.0")
        await g.get_directory()

        assert mock.await_count == 1
        expected_cmd = ["git", "clone", "prefect", "-b", "2.0.0", "--depth", "1"]
        assert mock.await_args[0][0][: len(expected_cmd)] == expected_cmd

    async def test_token_added_correctly_from_credential(self, monkeypatch):
        """Ensure that the repo url is in the format `https://<oauth-key>@github.com/<username>/<repo>.git`."""  # noqa: E501

        class p:
            returncode = 0

        mock = AsyncMock(return_value=p())
        monkeypatch.setattr(prefect.filesystems, "run_process", mock)
        credential = "XYZ"
        repo = "https://github.com/PrefectHQ/prefect.git"
        g = GitHub(
            repository=repo,
            access_token=credential,
        )
        await g.get_directory()
        assert mock.await_count == 1
        expected_cmd = [
            "git",
            "clone",
            f"https://{credential}@github.com/PrefectHQ/prefect.git",
            "--depth",
            "1",
        ]
        assert mock.await_args[0][0][: len(expected_cmd)] == expected_cmd

    async def test_ssh_fails_with_credential(self, monkeypatch):
        """Ensure that credentials cannot be passed in if the URL is not in the HTTPS
        format.
        """

        class p:
            returncode = 0

        mock = AsyncMock(return_value=p())
        monkeypatch.setattr(prefect.filesystems, "run_process", mock)
        credential = "XYZ"
        error_msg = "Crendentials can only be used with GitHub repositories using the 'HTTPS' format"  # noqa
        with pytest.raises(InvalidRepositoryURLError, match=error_msg):
            GitHub(
                repository="git@github.com:PrefectHQ/prefect.git",
                access_token=credential,
            )

    async def test_dir_contents_copied_correctly_with_get_directory(
        self, monkeypatch
    ):  # noqa
        """Check that `get_directory` is able to correctly copy contents from src->dst"""  # noqa

        class p:
            returncode = 0

        mock = AsyncMock(return_value=p())
        monkeypatch.setattr(prefect.filesystems, "run_process", mock)

        sub_dir_name = "puppy"

        with TemporaryDirectory() as tmp_src:
            parent_contents, child_contents = setup_test_directory(
                tmp_src, sub_dir_name
            )
            self.MockTmpDir.dir = tmp_src

            # move file contents to tmp_dst
            with TemporaryDirectory() as tmp_dst:
                monkeypatch.setattr(
                    prefect.filesystems,
                    "TemporaryDirectory",
                    self.MockTmpDir,
                )

                g = GitHub(
                    repository="https://github.com/PrefectHQ/prefect.git",
                )
                await g.get_directory(local_path=tmp_dst)

                assert set(os.listdir(tmp_dst)) == parent_contents
                assert set(os.listdir(Path(tmp_dst) / sub_dir_name)) == child_contents

    async def test_dir_contents_copied_correctly_with_get_directory_and_from_path(
        self, monkeypatch
    ):  # noqa
        """Check that `get_directory` is able to correctly copy contents from src->dst
        when `from_path` is included.

        It is expected that the directory specified by `from_path` will be moved to the
        specified destination, along with all of its contents.
        """

        class p:
            returncode = 0

        mock = AsyncMock(return_value=p())
        monkeypatch.setattr(prefect.filesystems, "run_process", mock)

        sub_dir_name = "puppy"

        with TemporaryDirectory() as tmp_src:
            parent_contents, child_contents = setup_test_directory(
                tmp_src, sub_dir_name
            )
            self.MockTmpDir.dir = tmp_src

            # move file contents to tmp_dst
            with TemporaryDirectory() as tmp_dst:
                monkeypatch.setattr(
                    prefect.filesystems,
                    "TemporaryDirectory",
                    self.MockTmpDir,
                )

                g = GitHub(
                    repository="https://github.com/PrefectHQ/prefect.git",
                )
                await g.get_directory(local_path=tmp_dst, from_path=sub_dir_name)

                assert set(os.listdir(tmp_dst)) == set([sub_dir_name])
                assert set(os.listdir(Path(tmp_dst) / sub_dir_name)) == child_contents
