# Publishing a Windows release

Kabuki-Cord release tags use the version in `pyproject.toml`, for example `v2.5.0`.
The Windows release workflow deliberately refuses to publish an unsigned installer.

## Required Authenticode credential

Use a code-signing certificate issued by a Windows-trusted certificate authority and
exported as a password-protected PFX. Do not use a self-signed certificate for public
releases, and never commit the PFX or its password.

Configure these repository Actions secrets:

- `WINDOWS_CODE_SIGNING_PFX_BASE64`: the PFX file encoded as one base64 string.
- `WINDOWS_CODE_SIGNING_PFX_PASSWORD`: the PFX export password.

The release runner imports the certificate into its temporary Current User store,
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
5. Watch the `Release` workflow. Do not create an unsigned release manually if it fails.
6. Download the published ZIP and verify the checksum and installer signature on a clean Windows machine.

To inspect a downloaded installer on Windows:

```powershell
Get-AuthenticodeSignature .\Install-Kabuki-Cord.exe | Format-List
```

The status must be `Valid` and the signer must be the expected publisher.
