import base64
import os
import logging
import sys

from cryptography.hazmat.bindings.openssl.binding import Binding
from pylibsrtp import Policy, Session

binding = Binding()
binding.init_static_locks()
ffi = binding.ffi
lib = binding.lib

SRTP_KEY_LEN = 16
SRTP_SALT_LEN = 14

current_dir = os.path.dirname(__file__)
root = os.path.dirname(current_dir)


CERT_PATH = os.path.join( root, 'certification/cert.pem')
KEY_PATH = os.path.join(root, 'certification/key.pem')
print(CERT_PATH)

logger = logging.getLogger('dtls')


def certificate_digest(x509):
    digest = lib.EVP_get_digestbyname(b'SHA256')
    if digest == ffi.NULL:
        raise ValueError("No such digest method")

    result_buffer = ffi.new("unsigned char[]", lib.EVP_MAX_MD_SIZE)
    result_length = ffi.new("unsigned int[]", 1)
    result_length[0] = len(result_buffer)

    digest_result = lib.X509_digest(x509, digest, result_buffer, result_length)
    assert digest_result == 1

    return b":".join([
        base64.b16encode(ch).upper() for ch
        in ffi.buffer(result_buffer, result_length[0])]).decode('ascii')


def get_srtp_key_salt(src, idx):
    key_start = idx * SRTP_KEY_LEN
    salt_start = 2 * SRTP_KEY_LEN + idx * SRTP_SALT_LEN
    return (
        src[key_start:key_start + SRTP_KEY_LEN] +
        src[salt_start:salt_start + SRTP_SALT_LEN]
    )


def is_rtcp(msg):
    return len(msg) >= 2 and msg[1] >= 192 and msg[1] <= 208


@ffi.callback('int(int, X509_STORE_CTX *)')
def verify_callback(x, y):
    return 1


class DtlsSrtpContext:
    def __init__(self):
        ctx = lib.SSL_CTX_new(lib.DTLS_method())
        self.ctx = ffi.gc(ctx, lib.SSL_CTX_free)

        lib.SSL_CTX_set_verify(self.ctx, lib.SSL_VERIFY_PEER | lib.SSL_VERIFY_FAIL_IF_NO_PEER_CERT,
                               verify_callback)
        if not lib.SSL_CTX_use_certificate_file(self.ctx,
                                                CERT_PATH.encode(sys.getfilesystemencoding()),
                                                lib.SSL_FILETYPE_PEM):
            print("SSL could not use certificate")
        if not lib.SSL_CTX_use_PrivateKey_file(self.ctx,
                                               KEY_PATH.encode(sys.getfilesystemencoding()),
                                               lib.SSL_FILETYPE_PEM):
            print("SSL could not use private key")
        if not lib.SSL_CTX_set_cipher_list(self.ctx, b'HIGH:!CAMELLIA:!aNULL'):
            print("SSL could not set cipher list")
        if lib.SSL_CTX_set_tlsext_use_srtp(self.ctx, b'SRTP_AES128_CM_SHA1_80'):
            print("SSL could not enable SRTP extension")
        # if lib.SSL_CTX_set_read_ahead(self.ctx, 1):
        #     print("SSL could not enable read ahead")


class DtlsSrtpSession:
    def __init__(self, context, is_server, transport):
        self.encrypted = False
        self.is_server = is_server
        self.remote_fingerprint = None
        self.transport = transport

        ssl = lib.SSL_new(context.ctx)
        self.ssl = ffi.gc(ssl, lib.SSL_free)

        self.read_bio = lib.BIO_new(lib.BIO_s_mem())
        self.write_bio = lib.BIO_new(lib.BIO_s_mem())
        lib.SSL_set_bio(self.ssl, self.read_bio, self.write_bio)

        if self.is_server:
            lib.SSL_set_accept_state(self.ssl)
        else:
            lib.SSL_set_connect_state(self.ssl)

    @property
    def local_fingerprint(self):
        x509 = lib.SSL_get_certificate(self.ssl)
        return certificate_digest(x509)

    async def connect(self):
        while not self.encrypted:
            result = lib.SSL_do_handshake(self.ssl)
            if result > 0:
                self.encrypted = True
                break

            error = lib.SSL_get_error(self.ssl, result)

            await self._write_ssl()

            if error == lib.SSL_ERROR_WANT_READ:
                data = await self.transport.recv()
                lib.BIO_write(self.read_bio, data, len(data))
            else:
                raise Exception('DTLS handshake failed (error %d)' % error)

        await self._write_ssl()

        # check remote fingerprint
        x509 = lib.SSL_get_peer_certificate(self.ssl)
        remote_fingerprint = certificate_digest(x509)
        if remote_fingerprint != self.remote_fingerprint.upper():
            raise Exception('DTLS fingerprint does not match')

        # generate keying material
        buf = ffi.new("char[]", 2 * (SRTP_KEY_LEN + SRTP_SALT_LEN))
        extractor = b'EXTRACTOR-dtls_srtp'
        if not lib.SSL_export_keying_material(self.ssl, buf, len(buf),
                                              extractor, len(extractor),
                                              ffi.NULL, 0, 0):
            raise Exception('DTLS could not extract SRTP keying material')

        view = ffi.buffer(buf)
        if self.is_server:
            srtp_tx_key = get_srtp_key_salt(view, 1)
            srtp_rx_key = get_srtp_key_salt(view, 0)
        else:
            srtp_tx_key = get_srtp_key_salt(view, 0)
            srtp_rx_key = get_srtp_key_salt(view, 1)

        logger.info('DTLS handshake complete')
        rx_policy = Policy(key=srtp_rx_key, ssrc_type=Policy.SSRC_ANY_INBOUND)
        self._rx_srtp = Session(rx_policy)
        tx_policy = Policy(key=srtp_tx_key, ssrc_type=Policy.SSRC_ANY_OUTBOUND)
        self._tx_srtp = Session(tx_policy)

    async def recv(self):
        data = await self.transport.recv()
        if is_rtcp(data):
            data = self._rx_srtp.unprotect_rtcp(data)
            logger.debug('Unprotected RTCP data %d bytes', len(data))
        else:
            data = self._rx_srtp.unprotect(data)
        return data

    async def send(self, data):
        if is_rtcp(data):
            logger.debug('Protecting RTCP data %d bytes', len(data))
            data = self._tx_srtp.protect_rtcp(data)
        else:
            data = self._tx_srtp.protect(data)
        await self.transport.send(data)

    async def _write_ssl(self):
        pending = lib.BIO_ctrl_pending(self.write_bio)
        if pending > 0:
            buf = ffi.new("char[]", pending)
            lib.BIO_read(self.write_bio, buf, len(buf))
            data = b''.join(buf)
            await self.transport.send(data)
