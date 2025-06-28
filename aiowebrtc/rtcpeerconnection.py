import asyncio 
import datetime 
import aioice 

from . import dtls

def get_ntp_seconds():
    return int ((datetime.datetime.utcnow() - datetime.datetime(1900, 1 ,1 ,0,0,0)).total_seconds() )
    
class RTCPeerConnection:
    def __init__(self):
        self.__dtlsContext = dtls.DtlsSrtpContext()
        self.__iceConnection = None #Interactive Connectivity Establishment
        self.__iceConnectionState = 'new'
        self.__iceGatheringState = 'new'
        
        self.__currentLocalDescription = None
        self.__currentRemoteDescription = None
    
    @property #getter
    def iceConnectionState(self):
        return self.__iceConnectionState
    
    @property
    def iceGatheringState(self):
        return self.__iceGatheringState
    
    @property
    def localDescription(self):
        return self.__currentLocalDescription
    
    @property
    def remoteDescription(self):
        return self.__currentRemoteDescription

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
            # create new ssl session - init DtlsSrtp Session
            #Creates a DtlsSrtpSession with is_server=False (server acts as DTLS client)
            self.__dtlsSession = dtls.DtlsSrtpSession(self.__dtlsContext, is_server=False, transport=self.__iceConnection)
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
                    self.__dtlsSession.remote_fingerprint = fingerprint
                elif attr == 'ice-ufrag':
                    self.__iceConnection.remote_username = value
                elif attr == 'ice-pwd':
                    self.__iceConnection.remote_password = value
        
        if self.__iceConnection.remote_candidates and self.iceConnectionState == 'new':
            asyncio.ensure_future(self.__connect())
        self.__currentRemoteDescription = sessionDescription
    
    async def setLocalDescription(self,sessionDescription):
        self.__currentLocalDescription = sessionDescription
    
    async def __gather(self):
        #change __iceGatheringState from new -->  gathering
        self.__iceGatheringState = 'gathering'
        await self.__iceConnection.gather_candidates() #gather local candidates
        #change __iceGatheringState from gathering -->  complete
        self.__iceGatheringState = 'complete'
    
    def __createSdp(self) :
        ntp_seconds = get_ntp_seconds()
        sdp = [
            'v=0',
            'o=- %d %d IN IP4 0.0.0.0' % (ntp_seconds, ntp_seconds),
            's=-',
            't= 0 0',
        ]
        default_candidate = self.__iceConnection.get_default_candidate(1)
        sdp += [
            # fix later: codec negotiate
            'm=audio %d UDP/TLS/RTP/SAVPF 0' % default_candidate.port,
            'c=IN IP4 %s' % default_candidate.host,
            'a=rtcp:9 IN IP4 0.0.0.0',
        ]
        for candidate in self.__iceConnection.local_candidates:
            sdp += ['a=candidate:%s' % candidate.to_sdp()]
        sdp += [
            'a=ice-pwd:%s' % self.__iceConnection.local_password,
            'a=ice-ufrag:%s' % self.__iceConnection.local_username,
            'a=fingerprint:sha-256 %s' % self.__dtlsSession.local_fingerprint,
        ]
        if self.__iceConnection.ice_controlling:
            sdp += ['a=setup:actpass']
        else:
            sdp += ['a=setup:active']
        sdp += ['a=sendrecv']
        sdp += ['a=rtcp-mux']
        #
        sdp += ['a=rtpmap:0 PCMU/8000']
        # list to long string using space, new line in between.
        return '\r\n'.join(sdp) + '\r\n'
            
