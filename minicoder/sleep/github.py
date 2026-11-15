"""GitHub dispatch: commit verified skill shards and read back published adapters.

Two paths, both real:
* **local git** (GitPython) when this checkout has a remote — commits on a
  dedicated ``sleep-skills`` branch and pushes with the ambient credentials.
* **GitHub API** (PyGithub) when a token is present, used for creating the
  branch, reading Release artifacts and checking workflow runs.

Nothing here fabricates a commit or a run: every return value comes from git
or the API response.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG
from minicoder.memory.db import sha256_file, utcnow

DEFAULT_BRANCH = "sleep-skills"
DATASET_DIR = "datasets/sleep_skills"


def _token() -> str | None:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    return None


@dataclass
class DispatchResult:
    pushed: bool
    method: str = ""
    repo: str = ""
    branch: str = ""
    commit: str = ""
    reason: str = ""
    url: str = ""


class GitHubDispatcher:
    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or CONFIG.paths.home).resolve()

    # ------------------------------------------------------------ helpers
    def _repo_slug(self) -> str:
        try:
            import git

            url = git.Repo(self.home).remotes.origin.url
            slug = url.split("github.com")[-1].lstrip(":/").removesuffix(".git")
            return slug
        except Exception:
            return ""

    def _checksum_sidecar(self, shard: Path) -> Path:
        side = shard.with_suffix(".sha256")
        side.write_text(f"{sha256_file(shard)}  {shard.name}\n", encoding="utf-8")
        return side

    # --------------------------------------------------------- local git
    def push_shard(self, shard: Path) -> dict[str, Any]:
        """Commit the shard to the sleep-skills branch via GitPython."""
        shard = Path(shard).resolve()
        side = self._checksum_sidecar(shard)
        try:
            import git
        except Exception as exc:
            return {"pushed": False, "reason": f"GitPython unavailable: {exc}"}
        try:
            repo = git.Repo(self.home)
        except Exception as exc:
            return {"pushed": False, "reason": f"not a git repo: {exc}"}
        if not repo.remotes:
            return {"pushed": False, "reason": "no git remote configured"}

        worktree = Path(tempfile.mkdtemp(prefix="mc_dispatch_"))
        try:
            # Isolated worktree on a dedicated branch: the user's checkout and
            # current branch are never touched by a sleep cycle.
            repo.git.worktree("add", "-B", DEFAULT_BRANCH, str(worktree))
            wt_repo = git.Repo(worktree)
            dest_dir = worktree / DATASET_DIR
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(shard, dest_dir / shard.name)
            shutil.copy2(side, dest_dir / side.name)
            manifest = dest_dir / "manifest.json"
            entries = []
            if manifest.exists():
                try:
                    entries = json.loads(manifest.read_text()).get("shards", [])
                except Exception:
                    entries = []
            entries.append({
                "file": shard.name,
                "sha256": sha256_file(shard),
                "examples": sum(1 for line in shard.read_text().splitlines() if line.strip()),
                "created_at": utcnow(),
                "cycle": True,
            })
            manifest.write_text(json.dumps({"shards": entries, "updated_at": utcnow()}, indent=2), encoding="utf-8")
            wt_repo.git.add(A=True)
            if not wt_repo.is_dirty():
                return {"pushed": False, "reason": "shard already committed"}
            wt_repo.index.commit(
                f"sleep: verified skill shard {shard.name}\n\n"
                f"examples={entries[-1]['examples']} sha256={entries[-1]['sha256'][:16]}\n"
                "Compiled by Project MiniCoder during a sleep cycle from VERIFIED skills only."
            )
            commit = wt_repo.head.commit.hexsha
            remote_url = repo.remotes.origin.url
            try:
                wt_repo.remotes.origin.push(f"{DEFAULT_BRANCH}:{DEFAULT_BRANCH}")
                pushed = True
                push_error = ""
            except Exception as exc:  # committed locally; push needs credentials
                pushed = False
                push_error = str(exc)[:300]
                log = CONFIG.paths.sleep_logs / "dispatch.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8") as fh:
                    fh.write(f"{utcnow()} commit={commit} push failed: {push_error}\n")
            if not pushed:
                return {
                    "pushed": False, "method": "git", "commit": commit, "branch": DEFAULT_BRANCH,
                    "reason": f"committed locally but push was rejected: {push_error}",
                    "url": remote_url,
                }
            slug = self._repo_slug()
            return {
                "pushed": True, "method": "git", "repo": slug, "branch": DEFAULT_BRANCH,
                "commit": commit, "url": f"https://github.com/{slug}/tree/{DEFAULT_BRANCH}/{DATASET_DIR}",
            }
        finally:
            try:
                import git

                git.Repo(self.home).git.worktree("remove", "--force", str(worktree))
            except Exception:
                shutil.rmtree(worktree, ignore_errors=True)
            try:
                import git

                git.Repo(self.home).git.worktree("prune")
            except Exception:
                pass

    # ----------------------------------------------------------- API path
    def api(self):
        token = _token()
        if not token:
            return None
        try:
            from github import Github

            return Github(token)
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        slug = self._repo_slug()
        info: dict[str, Any] = {
            "repo": slug,
            "token": bool(_token()),
            "branch": DEFAULT_BRANCH,
            "remote": "",
        }
        try:
            import git

            info["remote"] = git.Repo(self.home).remotes.origin.url
        except Exception:
            pass
        gh = self.api()
        if gh and slug:
            try:
                repo = gh.get_repo(slug)
                runs = list(repo.get_workflow_runs()[:3])
                info["workflow_runs"] = [
                    {"name": r.name, "status": r.status, "conclusion": r.conclusion,
                     "created_at": r.created_at.isoformat() if r.created_at else ""}
                    for r in runs
                ]
                try:
                    releases = list(repo.get_releases()[:3])
                    info["releases"] = [{"tag": rel.tag_name, "assets": [a.name for a in rel.get_assets()]}
                                        for rel in releases]
                except Exception:
                    info["releases"] = []
            except Exception as exc:
                info["error"] = str(exc)[:200]
        return info

    def pull_latest_adapter(self, dest_dir: Path | None = None) -> dict[str, Any]:
        """Download the newest released adapter (the WAKE half of the loop)."""
        gh = self.api()
        slug = self._repo_slug()
        if not gh or not slug:
            return {"pulled": False, "reason": "no GITHUB_TOKEN or no repo"}
        try:
            repo = gh.get_repo(slug)
            releases = list(repo.get_releases())
        except Exception as exc:
            return {"pulled": False, "reason": str(exc)[:200]}
        for rel in releases:
            for asset in rel.get_assets():
                if asset.name.endswith((".pt", ".safetensors")) and "adapter" in asset.name:
                    dest_dir = dest_dir or CONFIG.paths.checkpoints
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    out = dest_dir / asset.name
                    url = asset.browser_download_url
                    import urllib.request

                    urllib.request.urlretrieve(url, out)
                    return {"pulled": True, "tag": rel.tag_name, "asset": asset.name, "path": str(out)}
        return {"pulled": False, "reason": "no adapter asset found in releases"}
