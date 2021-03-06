import logging
import webapp2

from google.appengine.ext import db

from controllers.pubnub import Pubnub

class MulticastHandler(webapp2.RequestHandler):
	def post(self):
		station = self.request.get("station")
		data = self.request.get("data")
		
		# Init Pubnub object
		pubnub = Pubnub(
			"pub-9fb20153-b6bc-46c5-b7ea-82df49726e53", # PUBLISH KEY
			"sub-aa6b101e-24e9-11e1-ab04-3b69d50a7fd4", # SUBSCRIBE KEY
			"sec-24e1f724-8cae-4ad4-b3fe-f0dc84d32799", # SECRET KEY
			False, # SSL
		)
		
		# Publish to Pubnub
		state = pubnub.publish({
		    'channel' : station,
		    'message' : data,
		})
		
		logging.info("Broadcast state on %s via pubnub: %s" % (station, state))

		
		
