# Publishing a Windows release

Kabuki-Cord release tags use the version in `pyproject.toml`, for example `v2.5.0`.
The Windows release workflow signs automatically when both signing secrets are
configured. Otherwise, it publishes an unsigned installer and emits a prominent
warning in the workflow log and release notes.

## Optional Authenticode credential

Use a code-signing certificate issued by a Windows-trusted certificate authority and
exported as a password-protected PFX. Do not use a self-signed certificate for public
releases, and never commit the PFX or its password.

Configure these repository Actions secrets:

- `WINDOWS_CODE_SIGNING_PFX_BASE64`: the PFX file encoded as one base64 string.
- `WINDOWS_CODE_SIGNING_PFX_PASSWORD`: the PFX export password.

When configured, the release runner imports the certificate into its temporary Current User store,
builds and time-stamps `Install-Kabuki-Cord.exe`, verifies the Authenticode trust
status, packages the signed installer, runs privacy checks, and only then publishes
the ZIP and SHA-256 checksum.

If the certificate is hardware-backed or cannot be exported, use a managed signing
service such as Microsoft Trusted Signing instead of placing certificate material on
the runner. The workflow must still verify the completed installer before publishing.

## Release sequence

1. Merge the release commit into `main`.
2. Confirm `python scripts/check_version.py --tag vX.Y.Z` succeeds.
3. Confirm the test suite, secret scan, wheel verification, and release archive check pass.
4. Create and push the matching annotated tag, for example `v2.5.0`.
5. Watch the `Release` workflow and confirm whether its signing-mode message matches the intended release.
6. Download the published ZIP and verify its checksum on a clean Windows machine. If signing was enabled, also verify the installer signature.

To inspect a downloaded installer on Windows:

```powershell
Get-AuthenticodeSignature .\Install-Kabuki-Cord.exe | Format-List
```

For a signed release, the status must be `Valid` and the signer must be the expected
publisher. An intentionally unsigned release reports `NotSigned` and must be clearly
identified as unsigned in its release notes.
