import pytest
from pydantic import ValidationError

from coc_kp_assistant.domain import (
    SourceFileManifest,
    SourcePackKind,
    SourcePackManifest,
)


def test_source_pack_is_versioned_and_locked_to_coc7() -> None:
    manifest = SourcePackManifest(
        pack_id="coc7e.core.zh-v1.2.1",
        title="COC7 核心规则",
        version="1.2.1",
        kind=SourcePackKind.CORE,
        default_enabled=True,
        files=(
            SourceFileManifest(
                relative_path="core.pdf",
                media_type="application/pdf",
                sha256="a" * 64,
                page_count=400,
            ),
        ),
    )

    assert manifest.ruleset == "coc7e"
    assert manifest.files[0].page_count == 400


def test_source_file_cannot_escape_pack_root() -> None:
    with pytest.raises(ValidationError, match="stay inside"):
        SourceFileManifest(
            relative_path="../outside.pdf",
            media_type="application/pdf",
            sha256="b" * 64,
        )
