# Simple python server for Webrtc
- To create ssl certification for using https. Since getUserMedia can only used in https:
```
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

Sever will contain index.html
Start server :
```
python3 server.py
```