# Commit Message Examples

## Regular Project Example

```
linuxdrm: add widevine v18 support [1/1]

PD#SWPL-203865

Problem:
Widevine v18 is not supported in buildroot environment.

Solution:
Add 0001-support-buildroot.patch with:
- environment.py for toolchain configuration
- read_client_info.cpp for client info reading
- settings.gypi for compiler flags

Verify:
Build test on armhf and aarch64

Change-Id: I4a7e9c2f8b5d3e1a0f6c4b8d2e5a7f9c1b3d6e8a
Signed-off-by: teng.wang <teng.wang@amlogic.com>
```

## Media Project Example (Feature)

```
widevine: CF1 support client info from config file [1/1]

PD#TV-201551

Problem:
Widevine CDM client info only reads from environment variables,
does not support reading from /etc/widevine-property.conf or
/vendormodel/etc/widevine-property.conf for data separation.

Solution:
Update 0001-support-buildroot.patch to enhance read_client_info.cpp:
1. Add read_from_config_file() function to parse key=value format
2. Support multi-level priority lookup:
   - Environment variable (highest)
   - /etc/widevine-property.conf
   - /vendormodel/etc/widevine-property.conf
   - Default value (lowest)

Verify:
armhf and aarch64 build test

Change-Id: Ia27d19d782b4378429fc724113cdb372b08d41f5
Signed-off-by: teng.wang <teng.wang@amlogic.com>
```

## Media Project Example (Bug Fix)

```
media_hal: CB1 fix decoder crash on invalid input [1/1]

PD#SWPL-123456
BUG:123456789

Problem:
Media hal decoder crashes when receiving invalid input stream,
causing system instability during playback.

Solution:
Add input validation before processing:
1. Check buffer bounds before access
2. Return error code instead of crashing
3. Add null pointer checks

Verify:
Test with corrupted stream samples
Run stability test for 24 hours

Change-Id: I1234567890abcdef1234567890abcdef12345678
Signed-off-by: teng.wang <teng.wang@amlogic.com>
```

## GFX Project Example

```
gpu: optimize rendering pipeline [1/1]

PD#GFX-12345

Problem:
GPU rendering pipeline has performance bottleneck in texture upload,
causing frame drops in high resolution scenarios.

Solution:
Optimize texture upload path:
1. Use DMA-BUF for zero-copy transfer
2. Batch small texture updates
3. Add async upload support

Verify:
FPS test on 4K resolution content
Memory bandwidth test

Test:
Run gfxbench and compare scores
Manual test with 4K video playback

Change-Id: Iabcdef1234567890abcdef1234567890abcdef12
Signed-off-by: teng.wang <teng.wang@amlogic.com>
```

## DRM Project Example (Special Sign-off)

```
playready: CF1 add new license acquisition flow [1/1]

PD#DRM-54321

Problem:
Current license acquisition flow does not support new PlayReady
feature requirements for 2025 compliance.

Solution:
Implement new license acquisition:
1. Add support for XYZ feature
2. Update certificate handling
3. Add secure stop support

Verify:
Test with Microsoft test vectors
Compliance test suite pass

Change-Id: Id1234567890abcdef1234567890abcdef123456
Signed-off-by: DRM Auto Build <tao.guo@amlogic.com>
```

**Note**: DRM projects (vendor/playready, vendor/amlogic/mediahal_sdk, etc.)
must use `DRM Auto Build <tao.guo@amlogic.com>` for Signed-off-by.
