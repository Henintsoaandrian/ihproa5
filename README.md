# hacktiv8 

hacktiv8(formerly A5_Bypass_OSS) is an open-source research project focused on analyzing and experimenting with iOS activation proccess using itunesstored sandbox escape vulnerability. It provides a one-click cross-platform solution for bypassing activation on legacy iOS devices without the need of pwning.

## Disclaimer

This project is intended strictly for research and educational purposes.  
It is not designed for, and must not be used in, production environments or for unlawful activities.  
The authors and contributors take no responsibility for any misuse or damage caused to devices, data, or systems.

## Requirements

The both host and target devices must be connected to Wi-Fi at all times during operation.  
Network connectivity is mandatory for the application workflow to function correctly.

## Compatibility

The tool targets iOS 9 and 10 devices (and Wi-Fi-only devices on iOS 8).

## Backend Configuration

The backend URL is stored in the `BACKEND_URL` global constant of [`main.py`](https://github.com/overcast302/hacktiv8/blob/main/main.py#L18)

Due to legacy iOS devices lacking trust for modern certificate authorities, the backend must either use HTTP, or serve an SSL certificate that chains to a root CA trusted by legacy iOS. Modern certificate authorities such as Let's Encrypt are not trusted on legacy iOS versions and will cause HTTPS connections to fail on target devices.

## Credits
- [pkkf5673](https://github.com/bablaerrr)
- [bl_sbx](https://github.com/hanakim3945/bl_sbx)
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)

## License

Refer to the repository license file for licensing details.
