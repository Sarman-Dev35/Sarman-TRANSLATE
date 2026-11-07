# Windows code signing

The executable's file metadata identifies **Sarman Studios** as its company name. This is useful in File Explorer's Details tab, but it is not an Authenticode signature and does not establish a verified Windows publisher.

Windows displays the publisher from the Subject of the signing certificate. To show a verified publisher and satisfy Smart App Control when Microsoft's reputation service cannot make a confident decision, the release must be signed with a valid code-signing certificate issued by a trusted certificate authority. A self-signed certificate is not a substitute and can still be blocked.

## Existing GitHub Actions signing support

The Windows Build workflow signs every packaged EXE, DLL, and PYD file, verifies each signature with SignTool, and applies an RFC 3161 timestamp when these repository Actions secrets are configured:

- WINDOWS_CERTIFICATE_BASE64: the PFX certificate file encoded as Base64.
- WINDOWS_CERTIFICATE_PASSWORD: the PFX password.

To encode a PFX file in PowerShell, run:

    [Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\path\to\code-signing.pfx')) | Set-Clipboard

Add the values under the repository's Settings > Secrets and variables > Actions. Never commit the PFX file, its password, or the Base64 value to the repository. The certificate must include its private key and be valid for code signing.

The certificate authority controls which legal publisher name can be placed in the certificate. If the certificate is issued to an individual, Windows will display that verified individual's name; the executable's CompanyName metadata cannot override it to claim a different publisher. To display Sarman Studios as the verified publisher, the certificate provider must validate and issue the certificate under that publisher identity.

## Smart App Control and SmartScreen

A valid signature improves trust and identifies the publisher, but a newly published file may still receive a SmartScreen reputation warning while reputation accumulates. EV certificates no longer bypass SmartScreen warnings by default. Smart App Control also has no per-app allow-list bypass; do not disable Windows protection to run an unsigned build.

Microsoft Artifact Signing is another supported route for signing release binaries, but it requires identity verification and a separately configured account. The current workflow uses the PFX secrets above.
