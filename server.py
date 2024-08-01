import json 
import logging
import os 

import sys 
from aiohttp import web
import ssl
from aiowebrtc import RTCPeerConnection


ROOT = os.path.dirname(__file__)
# print(ROOT)

#Please modify ssl certificaiton path 
cert_path = os.path.join(ROOT,'certification/cert.pem')
cert_key_path = os.path.join(ROOT,'certification/key.pem')

# print(cert_path)
async  def index(request):
    #read content HTML in dir
    html = open(os.path.join(ROOT,'index.html'),'r').read()
    return web.Response(content_type='text/html',text=html)

async def offer(request):
    print(f'request from client {request}')
    offer = await request.json()
    #create peer connection
    pc = RTCPeerConnection()
    #save offer-client
    await pc.setRemoteDescription(offer)
    #generate answer to offer 
    answer = await pc.createAnswer()
    print(answer)
    await pc.setLocalDescription(answer)
    return web.Response(content_type='application/json',
                        text=json.dumps(pc.localDescription))
    
def main():
    app = web.Application()
    
    app.add_routes([
        web.get('/',index),
        web.post('/offer',offer)
    ])

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(cert_path,cert_key_path)

    web.run_app(app, host='192.168.2.2', port=8081, ssl_context=ssl_context)
    # site = web.TCPSite(runner, 'localhost', 4443)
    # await site.start()
    print("Server running on https://192.168.2.2:8081")
 

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # asyncio.run(main(), debug=True)
    main()