# -*- coding: UTF-8 -*-

import socket
from struct import pack, unpack

from librouteros.exc import ConnError, LibError
from librouteros.api import Api




def enclen( length ):
    '''
    Encode given length in mikrotik format.

    length: Integer < 268435456.
    returns: Encoded length in bytes.
    '''

    if length < 128:
        ored_length = length
        offset = -1
    elif length < 16384:
        ored_length = length | 0x8000
        offset = -2
    elif length < 2097152:
        ored_length = length | 0xC00000
        offset = -3
    elif length < 268435456:
        ored_length = length | 0xE0000000
        offset = -4
    else:
        raise ConnError( 'unable to encode length of {0}'
                        .format( length ) )

    encoded_length = pack( '!I', ored_length )[offset:]
    return encoded_length


def declen( bytes_string ):
    '''
    Decode length based on given bytes.

    bytes_string: Bytes string to decode.
    returns: Length in integer.
    '''

    bytes_length = len( bytes_string )

    if bytes_length < 2:
        offset = b'\x00\x00\x00'
        XOR = 0
    elif bytes_length < 3:
        offset = b'\x00\x00'
        XOR = 0x8000
    elif bytes_length < 4:
        offset = b'\x00'
        XOR = 0xC00000
    elif bytes_length < 5:
        offset = b''
        XOR = 0xE0000000

    combined_bytes = offset + bytes_string
    decoded = unpack( '!I', combined_bytes )[0]
    decoded ^= XOR

    return decoded


def decsnt( sentence ):

    return tuple( word.decode( 'UTF-8', 'strict' ) for word in sentence )


def encsnt( sentence ):
    '''
    Encode given sentence in API format.

    returns: Encoded sentence in bytes object.
    '''

    encoded = map( encword, sentence )
    encoded = b''.join( encoded )
    # append EOS byte
    encoded += b'\x00'

    return encoded


def encword( word ):
    '''
    Encode word in API format.

    returns: Encoded word in bytes object.
    '''
    encoded_len = enclen( len( word ) )
    encoded_word = word.encode( encoding = 'utf_8', errors = 'strict' )
    return encoded_len + encoded_word








class ReaderWriter:


    def __init__( self, sock ):
        self.sock = sock


    def writeSentence( self, sentence ):
        '''
        Write sentence to connection.

        sentence: Iterable (tuple or list) with words.
        '''

        encoded = encsnt( sentence )
        self.writeSock( encoded )


    def readSentence( self ):
        '''
        Read sentence from connection.

        returns: Sentence as tuple with words in it.
        '''

        sentence = []
        to_read = self.getLength()

        while to_read:
            word = self.readSock( to_read )
            sentence.append( word )
            to_read = self.getLength()

        decoded_sentence = decsnt( sentence )

        return decoded_sentence


    def readSock( self, length ):
        '''
        Read as many bytes from socket as specified in length.
        Loop as long as every byte is read unless exception is raised.
        '''

        return_string = b''
        to_read = length
        total_bytes_read = 0

        try:
            while to_read:
                read = self.sock.recv( to_read )
                return_string += read
                to_read -= len( read )
                total_bytes_read = length - to_read

                if not read:
                    raise ConnError( 'connection unexpectedly closed. read {read}/{total} bytes.'
                                    .format( read = total_bytes_read, total = length ) )
        except socket.timeout:
            raise ConnError( 'socket timed out. read {read}/{total} bytes.'
                            .format( read = total_bytes_read, total = length ) )
        except socket.error as estr:
            raise ConnError( 'failed to read from socket: {reason}'.format( reason = estr ) )

        return return_string


    def writeSock( self, string ):
        '''
        Writt given string to socket. Loop as long as every byte in
        string is written unless exception is raised.
        '''

        string_length = len( string )
        total_bytes_sent = 0

        try:
            while string:
                sent = self.sock.send( string )
                # remove sent bytes from begining of string
                string = string[sent:]
                total_bytes_sent = string_length - len( string )

                if not sent:
                    raise ConnError( 'connection unexpectedly closed. sent {sent}/{total} bytes.'
                                    .format( sent = total_bytes_sent, total = string_length ) )
        except socket.timeout:
            raise ConnError( 'socket timed out. sent {sent}/{total} bytes.'
                            .format( sent = total_bytes_sent, total = string_length ) )
        except socket.error as estr:
            raise ConnError( 'failed to write to socket: {reason}'.format( reason = estr ) )


    def getLength( self ):
        '''
        Read encoded length and return it as integer.
        '''

        first_byte = self.readSock( 1 )
        first_byte_int = unpack( 'B', first_byte )[0]

        if first_byte_int < 128:
            bytes_to_read = 0
        elif first_byte_int < 192:
            bytes_to_read = 1
        elif first_byte_int < 224:
            bytes_to_read = 2
        elif first_byte_int < 240:
            bytes_to_read = 3
        else:
            raise ConnError( 'unknown controll byte received {0!r}'
                            .format( first_byte ) )

        additional_bytes = self.readSock( bytes_to_read )
        bytes_string = first_byte + additional_bytes
        decoded = declen( bytes_string )

        return decoded


    def close( self ):

        if self.sock._closed:
            return
        # shutdown socket
        try:
            self.sock.shutdown( socket.SHUT_RDWR )
        except socket.error:
            pass
        finally:
            self.sock.close()


class Connection:


    def __init__( self, drv ):
        self.drv = drv


    def _set_timeout(self, value):
        if value < 1:
            raise ValueError('timeout must be greater than 0')
        else:
            self.drv.conn.sock.settimeout(value)

    def _get_timeout(self):
        return self.drv.conn.sock.gettimeout()

    timeout = property( _get_timeout, _set_timeout, doc='Get or set timeout of connection. Timeout muste be > 0.' )


    def api( self ):
        '''
        Return a new instance of class Api.
        '''

        return Api( self.drv )


    def close( self ):
        '''
        Send /quit and close the connection.
        '''

        try:
            self._send_quit()
        except LibError:
            pass
        finally:
            self.drv.close()


    def _send_quit( self ):
        '''
        Send /quit command.
        '''
        self.drv.writeSnt( '/quit', () )
        self.drv.readSnt()


    def __del__( self ):
        '''
        On garbage collection run close().
        '''
        self.close()
