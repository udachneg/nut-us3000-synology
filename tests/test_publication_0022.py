"""Historical 0022 assets and current source closure; no Docker/NAS changes."""
import hashlib
from pathlib import Path
import re
import subprocess
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPK = 'nut-us3000_epyc7002-7.2_2.8.5-0022.spk'
SPK_HASH = 'cd3fbec1def596f4048a0280e6734e4d37d66c10c77e84a3763af3988c2ca72f'
SOURCE_MANIFEST = 'release/PACKAGE-SOURCE-0025.sha256'
CURRENT_SPK = 'nut-us3000_epyc7002-7.2_2.8.5-0025.spk'
CURRENT_HASH = 'e89d90f2c2efb1742077887c4ab5f6aa1caa7827936d0c3a0623745d0ac8e436'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(path):
    entries = {}
    for line in path.read_text().splitlines():
        value, name = line.split('  ', 1)
        if name in entries or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('duplicate path or invalid hash')
        entries[name] = value
    return entries


def distributed_paths():
    if (ROOT / '.git').exists():
        return list(filter(None, subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')))
    # GitHub source archives have no .git directory; inspect their actual files.
    return [str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()
            and not {'artifacts', '__pycache__'}.intersection(p.relative_to(ROOT).parts)]


class Publication0022Test(unittest.TestCase):
    def test_complete_spk_source_matches_build_snapshot(self):
        expected = manifest(ROOT / SOURCE_MANIFEST)
        actual = {str(p.relative_to(ROOT)): digest(p)
                  for p in (ROOT / 'spk').rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(expected, actual)
        self.assertFalse(any(p.is_symlink() for p in (ROOT / 'spk').rglob('*')))

    def test_source_manifest_is_exactly_the_git_distributed_source_set(self):
        expected = manifest(ROOT / SOURCE_MANIFEST)
        self.assertEqual(set(expected), {p for p in distributed_paths() if p.startswith('spk/')})

    def test_release_assets_match_all_published_checksums(self):
        checksums = manifest(ROOT / 'release/SHA256SUMS-0022.txt')
        expected_names = {SPK, SPK + '.sha256', 'nut-2.8.5.tar.gz',
                          'libusb-1.0.29.tar.bz2', 'nut-2.8.5.tar.gz.sig',
                          'nut-key.gpg', 'BUILD-PROVENANCE-0022.txt',
                          'normalized-manifest.json', 'normalized-manifest-0022.sha256',
                          'PACKAGE-SOURCE-0022.sha256'}
        self.assertEqual(expected_names, set(checksums))
        for name, value in checksums.items():
            self.assertEqual(value, digest(ROOT / 'artifacts' / name), name)
        self.assertEqual(SPK_HASH, checksums[SPK])

    def test_spk_identity_and_checksum_files(self):
        path = ROOT / 'artifacts' / SPK
        self.assertEqual(SPK_HASH, digest(path))
        self.assertEqual({SPK: SPK_HASH}, manifest(path.with_suffix('.spk.sha256')))
        with tarfile.open(path, 'r:') as archive:
            info = archive.extractfile('INFO').read().decode()
        for field in ('version="2.8.5-0022"', 'package="nut-us3000"', 'arch="epyc7002"'):
            self.assertIn(field, info)
        self.assertEqual({'normalized-manifest.json': digest(ROOT / 'artifacts/normalized-manifest.json')},
                         manifest(ROOT / 'artifacts/normalized-manifest-0022.sha256'))

    def test_upstream_source_inputs(self):
        for name, value in manifest(ROOT / 'spk/sources/source-manifest.sha256').items():
            self.assertEqual(value, digest(ROOT / name), name)

    def test_instructions_and_completed_gate(self):
        for name, delay, deny in [('README.md', '**5 minutes**', 'deny'),
                                  ('README_RU.md', '**5 минут**', 'запрет')]:
            text = (ROOT / name).read_text()
            for token in ('v2.8.5-0025-rc1)', CURRENT_SPK, CURRENT_HASH, '10.255.255.1', 'TCP 3493', delay,
                          'Arc Apps & Permissions', 'RAM', '65535', deny):
                self.assertIn(token, text)
        current = (ROOT / 'docs/VALIDATION.md').read_text()
        for token in ('RC_TESTED_UPGRADE', '0022 → 0025', CURRENT_HASH,
                      'No new full safe-mode', 'remain unverified'):
            self.assertIn(token, current)
        validation = (ROOT / 'docs/VALIDATION_0022.md').read_text()
        for token in ('FINAL_TESTED_HOST', 'did **not** produce a formal PASS',
                      'keep-data', 'preconfigured host', 'not part', 'explicit approval',
                      '614 seconds', 'not separately captured', 'not repeated'):
            self.assertIn(token, validation)
        notes = (ROOT / 'release/RELEASE-NOTES-0022.md').read_text()
        for token in (SPK_HASH, 'v2.8.5-0022/README_RU.md', 'no rebuild',
                      '614 seconds', 'formal PASS'):
            self.assertIn(token, notes)
        notes = (ROOT / 'release/RELEASE-NOTES-0025-RC1.md').read_text()
        for token in (CURRENT_HASH, 'v2.8.5-0025-rc1/README_RU.md',
                      'no rebuild for publication', 'not yet runtime-validated'):
            self.assertIn(token, notes)

    def test_current_document_links_resolve(self):
        paths = [ROOT / n for n in ('README.md', 'README_RU.md', 'docs/BUILDING.md',
                 'docs/VALIDATION.md', 'THIRD_PARTY_NOTICES.md', 'SECURITY.md')]
        for path in paths:
            for link in re.findall(r'\[[^]]+\]\(([^)]+)\)', path.read_text()):
                if '://' not in link and not link.startswith('#'):
                    self.assertTrue((path.parent / link.split('#')[0]).is_file(), link)

    def test_public_index_has_no_private_paths_or_artifacts(self):
        names = distributed_paths()
        forbidden = ('/Users/' + 'ehlopenko', 'quickconnect' + '.to',
                     'ehlopenko' + '5463w', '@gmail' + '.com', '@yandex' + '.ru')
        for name in filter(None, names):
            self.assertFalse(any(x in Path(name).parts for x in
                                 ('diagnostics', '.superpowers', 'live', '__pycache__', 'artifacts')))
            self.assertNotEqual('.spk', Path(name).suffix)
            path = ROOT / name
            if not path.exists():
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for token in forbidden:
                self.assertNotIn(token, text, name)


if __name__ == '__main__':
    unittest.main()
