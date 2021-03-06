import logging
from datetime import datetime

import json
import webapp2

from google.appengine.ext import db
from google.appengine.api.taskqueue import Task

from controllers.base import BaseHandler
from controllers.base import login_required

from models.api.station import StationApi

from models.db.track import Track
from models.db.broadcast import Broadcast
from models.db.like import Like

class TrackDeleteHandler(webapp2.RequestHandler):
	def delete(self):
		cursor = self.request.get("cursor")
		track_id = self.request.get("track_id")
		typeModel = self.request.get("type")

		if(track_id):
			track = Track.get_by_id(int(track_id))
			logging.info("Getting from datastore track with track_id = " + track_id)

			if(track):
				logging.info("Track found")

				if(typeModel == "broadcast"):
					# Deleting broadcasts associated to track
					query = Broadcast.all()
					query.filter("track", track)

					if(cursor):
						logging.info("Cursor found")
						query.with_cursor(start_cursor = cursor)

					broadcasts = query.fetch(100)
					logging.info("Fetched : %d Broadcast(s) from datastore."%(len(broadcasts)))
					
					if(len(broadcasts)>0):
						db.delete(broadcasts)
						logging.info("Deleted : %d Broadcast(s) from datastore."%(len(broadcasts)))

						task = Task(
							method = 'DELETE',
							url = "/taskqueue/deletetrack",
							params = {
								"cursor": cursor,
								"track_id": track_id,
								"type": typeModel,
							}
						)
						task.add(queue_name="worker-queue")
					else:
						task = Task(
							method = 'DELETE',
							url = "/taskqueue/deletetrack",
							params = {
								"track_id": track_id,
								"type": "like",
							}
						)
						task.add(queue_name="worker-queue")

				elif (typeModel == "like"):
					# Deleting likes associated to track
					query = Like.all()
					query.filter("track", track)
					
					if(cursor):
						logging.info("Cursor found")
						query.with_cursor(start_cursor = cursor)

					like = query.get()

					if like is None:
						logging.info("No like for this track, deleting track.")
						track.delete()
					else:
						try:
							listener_proxy = StationApi(like.listener.shortname)
							listener_proxy.decrement_likes_counter()
							logging.info("Listener Like counter decremented")
						except:
							logging.info("User has not created a station (likes used to be linked to user to stations)")
						
						Track.decrement_likes_counter(track.key().id())
						logging.info("Track likes counter decremented")

						like.delete()
						logging.info("Like deleted from datastore")

						cursor = query.cursor()

						task = Task(
							method = 'DELETE',
							url = "/taskqueue/deletetrack",
							params = {
								"cursor": cursor,
								"track_id": track_id,
								"type": typeModel,
							}
						)
						task.add(queue_name="worker-queue")
						
				response = True
		else:
			response = False
		self.response.out.write(json.dumps({ "response": response }))
