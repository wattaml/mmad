# Media Projects List

The following projects must use media project commit format:
`media_module: CF1/CB1 description [1/1]`

## Project List

From check_format.py `media_pro_list`:

- av-restricted/platform/vendor/AmFFmpegAdapter
- av-restricted/platform/vendor/amnuplayer
- av-restricted/platform/vendor/media_hal
- av-restricted/platform/hardware/amlogic/omx
- av-restricted/platform/trustedapp/widevine
- av-restricted/platform/vendor/widevine
- av-restricted/platform/trustedapp/playready
- av-restricted/platform/vendor/playready
- av-restricted/platform/vendor/netflix_mgkid
- av-restricted/platform/vendor/libsecmem
- av-restricted/platform/trustedapp/video_firmware
- av-restricted/vendor/amlogic/video/ucode
- platform/hardware/amlogic/media_modules
- platform/external/ffmpeg-aml
- vendor/amlogic/codec2
- vendor/amlogic/mediahal_sdk

## CF/CB Classification

### CF (CL Feature)
- **CF0**: Critical feature development or optimization
- **CF1**: Important feature development or optimization
- **CF2**: Normal feature development or optimization

### CB (CL Bug)
- **CB0**: Critical bug
- **CB1**: Important bug
- **CB2**: Normal bug

## Example Subject Lines

```
widevine: CF1 add v20 build config [1/1]
media_hal: CB2 fix memory leak in decoder [1/1]
omx: CF0 optimize buffer allocation [1/1]
```
