import asyncio 
import datetime 
import aioice 


def get_ntp_seconds():
    return int ((datetime.datetime.utcnow() - datetime.datetime(1900, 1 ,1 ,0,0,0)).total_seconds() )
    
class RTCPeerConnection:
    def __init__(self):
        #self.__dtlsContext = dtls.DtlsSrtpContext()
        self.__iceConnection = None
        self.__iceConnectionState = 'new'
        self.__iceGatheringState = 'new'
    
    @property #getter
    def iceConnectionState(self):
        return self.__iceConnectionState
    
    @property
    def iceGatheringState(self):
        return self.__iceGatheringState

    async def createAnswer(self):
        """ Create SDP answer to an offer  as json object
        """
        return {
            'sdp': self.__createSdp(),
            'type' : 'answer'
        }

    async def createOffer(self):
        """ Create a SDP offer when starting a new WebRTC
        """

    #save details from client/other_peer
    async def setRemoteDescription(self,sessionDescription):
        if self.__iceConnection is None :
            self.__iceConnection = aioice.Connection(ice_controlling=False)
            # self.dtlsSession = dtls.DtlsSrtpSession(self.__dtlsContext, is_server=False, tranport=self.__iceConnection)
            await self.__gather()
        #unpack SDP offer
        for line in sessionDescription['sdp'].splitlines():
            if line.startswith('a=') and ':' in line:
                #take strings second charater, split by first ':' only -> attribute , value
                attr, value = line[2:].split(':',1)
            #save remote candidate: ip,port
            if attr == 'candidate':
                self.__iceConnection.remote_candidates.append(aioice.Candidate.from_sdp(value))
            elif attr == 'fingerprint':
                algo, fingerprint = value.split()
                assert algo == 'sha-256',f'needs to be sha-256'
                #self.__dtlsSession.remote_fingerprint == fingerprint
            elif attr == 'ice-ufrag':
                self.__iceConnection.remote_username = value
            elif attr == 'ice-pwd':
                self.__iceConnection.remote_password = value
        
        if self.__iceConnection.remote_candidates and self.iceConnectionState == 'new':
            asyncio.ensure_future(self.__connect())
    
            
    
    async def __gather(self):
        self.__iceGatheringState = 'gathering'
        await self.__iceConnection.gather_candidates() #gather local candidates
        self.__iceGatheringState = 'complete'
    
    async def __createSdp(self) :
        ntp_seconds = get_ntp_seconds()
            