import json 
import logging
import os 

import sys 
from aiohttp import web


ROOT = os.path.dirname(__file__)
print(ROOT)

async  def index(request):
    #read content HTML in dir
    html = open(os.path.join(ROOT,'index.html','r')).read()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    #create app instance
    app = web.Application()
    #router
    app.router.add_get('/',index)
    #start server 
    web.run_app(app, host='127.0.0.1', port=8081)