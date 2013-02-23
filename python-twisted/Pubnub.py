## www.pubnub.com - PubNub Real-time push service in the cloud. 
# coding=utf8

## PubNub Real-time Push APIs and Notifications Framework
## Copyright (c) 2010 Stephen Blum
## http://www.pubnub.com/

## -----------------------------------
## PubNub 3.1 Real-time Push Cloud API
## -----------------------------------
import sys
import json
import time
import hashlib
import urllib2
import uuid
sys.path.append('../')
sys.path.append('../../')
sys.path.append('../../../')
from PubnubCoreAsync import PubnubCoreAsync
try:
    from hashlib import sha256
    digestmod = sha256
except ImportError:
    import Crypto.Hash.SHA256 as digestmod
    sha256 = digestmod.new
import hmac
from twisted.web.client import getPage
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.client import HTTPConnectionPool
from twisted.web.http_headers import Headers
from PubnubCrypto import PubnubCrypto
import gzip
import zlib

pnconn_pool = HTTPConnectionPool(reactor)
pnconn_pool.maxPersistentPerHost    = 100
pnconn_pool.cachedConnectionTimeout = 310

class Pubnub(PubnubCoreAsync):

    def start(self): reactor.run()
    def stop(self):  reactor.stop()
    def timeout( self, callback, delay ):
        reactor.callLater( delay, callback )

    def __init__(
        self,
        publish_key,
        subscribe_key,
        secret_key = False,
        cipher_key = False,
        ssl_on = False,
        origin = 'pubsub.pubnub.com'
    ) :
        super(Pubnub, self).__init__(
            publish_key,
            subscribe_key,
            secret_key,
            ssl_on,
            origin,
        )        

    def subscribe( self, args ) :
        """
        #**
        #* Subscribe
        #*
        #* This is NON-BLOCKING.
        #* Listen for a message on a channel.
        #*
        #* @param array args with channel and message.
        #* @return false on fail, array on success.
        #**

        ## Subscribe Example
        def receive(message) :
            print(message)
            return True

        ## On Connect Callback
        def connected() :
            pubnub.publish({
                'channel' : 'hello_world',
                'message' : { 'some_var' : 'text' }
            })

        ## Subscribe
        pubnub.subscribe({
            'channel'  : 'hello_world',
            'connect'  : connected,
            'callback' : receive
        })

        """
        ## Fail if missing channel
        if not 'channel' in args :
            return 'Missing Channel.'

        ## Fail if missing callback
        if not 'callback' in args :
            return 'Missing Callback.'

        ## Capture User Input
        channel   = str(args['channel'])
        callback  = args['callback']
        connectcb = args['connect']

        if 'errorback' in args:
            errorback = args['errorback']
        else:
            errorback = lambda x: x

        ## New Channel?
        if not (channel in self.subscriptions) :
            self.subscriptions[channel] = {
                'first'     : False,
                'connected' : 0,
                'timetoken' : '0'
            }

        ## Ensure Single Connection
        if self.subscriptions[channel]['connected'] :
            return "Already Connected"

        self.subscriptions[channel]['connected'] = 1

        ## SUBSCRIPTION RECURSION 
        def substabizel():
            ## STOP CONNECTION?
            if not self.subscriptions[channel]['connected']:
                return

            def sub_callback(response):
                ## STOP CONNECTION?
                if not self.subscriptions[channel]['connected']:
                    return

                ## CONNECTED CALLBACK
                if not self.subscriptions[channel]['first'] :
                    self.subscriptions[channel]['first'] = True
                    connectcb()

                ## PROBLEM?
                if not response:
                    def time_callback(_time):
                        if not _time:
                            reactor.callLater( 1, substabizel )
                            return errorback("Lost Network Connection")
                        else:
                            reactor.callLater( 1, substabizel )

                    ## ENSURE CONNECTED (Call Time Function)
                    return self.time({ 'callback' : time_callback })

                self.subscriptions[channel]['timetoken'] = response[1]
                substabizel()

                pc = PubnubCrypto()
                out = []
                for message in response[0]:
                     if self.cipher_key :
                          if type( message ) == type(list()):
                              for item in message:
                                  encryptItem = pc.decrypt(self.cipher_key, item )
                                  out.append(encryptItem)
                              message = out
                          elif type( message ) == type(dict()):
                              outdict = {}
                              for k, item in message.iteritems():
                                  encryptItem = pc.decrypt(self.cipher_key, item )
                                  outdict[k] = encryptItem
                                  out.append(outdict)
                              message = out[0]
                          else:
                              message = pc.decrypt(self.cipher_key, message )
                     else :
                          message

                     callback(message)

            ## CONNECT TO PUBNUB SUBSCRIBE SERVERS
            try :
                self._request( [
                    'subscribe',
                    self.subscribe_key,
                    channel,
                    '0',
                    str(self.subscriptions[channel]['timetoken'])
                ], sub_callback )
            except :
                reactor.callLater( 1, substabizel )
                return

        ## BEGIN SUBSCRIPTION (LISTEN FOR MESSAGES)
        substabizel()


    def unsubscribe( self, args ):
        channel = str(args['channel'])
        if not (channel in self.subscriptions):
            return False

        ## DISCONNECT
        self.subscriptions[channel]['connected'] = 0
        self.subscriptions[channel]['timetoken'] = 0
        self.subscriptions[channel]['first']     = False

    def time( self, args ) :
        """
        #**
        #* Time
        #*
        #* Timestamp from PubNub Cloud.
        #*
        #* @return int timestamp.
        #*

        ## PubNub Server Time Example
        def time_complete(timestamp):
            print(timestamp)

        pubnub.time(time_complete)

        """
        def complete(response) :
            if not response: return 0
            args['callback'](response[0])

        self._request( [
            'time',
            '0'
        ], complete )

    def uuid(self) :
        """
        #**
        #* uuid
        #*
        #* Generate a UUID
        #*
        #* @return  UUID.
        #*

        ## PubNub UUID Example
        uuid = pubnub.uuid()
        print(uuid)
        """
        return uuid.uuid1()

    def _request( self, request, callback, timeout=30 ) :
        global pnconn_pool

        ## Build URL
        url = self.origin + '/' + "/".join([
            "".join([ ' ~`!@#$%^&*()+=[]\\{}|;\':",./<>?'.find(ch) > -1 and
                hex(ord(ch)).replace( '0x', '%' ).upper() or
                ch for ch in list(bit)
            ]) for bit in request])

        requestType = request[0]
        agent       = Agent(
            reactor,
            self.ssl and None or pnconn_pool,
            connectTimeout=timeout
        )
        print url
        gp  = getPage( url, headers={
            'V'               : ['3.4'],
            'User-Agent'      : ['Python-Twisted'],
            'Accept-Encoding' : ['gzip']
        } );
        
        gp.addCallback(callback)
        gp.addErrback(callback)
	   

class PubNubResponse(Protocol):
    def __init__( self, finished ):
        self.finished = finished

    def dataReceived( self, bytes ):
            self.finished.callback(bytes)
