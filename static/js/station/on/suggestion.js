// ---------------------------------------------------------------------------
// SUGGESTION MANAGER
// ---------------------------------------------------------------------------

SuggestionManager.prototype = new RealtimeTabManager();
SuggestionManager.prototype.constructor = SuggestionManager;

function SuggestionManager(station_client){
	RealtimeTabManager.call(this, station_client);
	
	// Settings
	this.url = "/api/suggestions";
	this.data_type = "json";
	
	// UI Settings
	this.name = "#suggestions-tab";
	this.selector = this.name + " .tab-items";
	
	// Additional attributes
	this.suggestion_on = true;
	this.alert_manager = new AlertManager(station_client, "New suggestion!", "#suggestions-header");
	
	// Init methods
	this.previewListen();
	this.processListen();
}

SuggestionManager.prototype.serverToLocalItem = function(raw_item){
	var new_suggestion = raw_item;
	new_suggestion["track_id"] = null;
	new_suggestion["track_created"] = null;
	
	var item = {
		id: new_suggestion.key_name,
		created: new_suggestion.created,
		content: new_suggestion,
	}
	return item
}

SuggestionManager.prototype.postSubmit = function(btn, item){
	
	if(this.suggestion_on){
		// Suggestion authorized
		var content = item.content
		var youtube_title = content.youtube_title
		var youtube_thumbnail = "http://i.ytimg.com/vi/" + content.youtube_id + "/default.jpg"
		
		// Update fancy box content
		$("#popup-suggestion span.clip").append($("<img/>").attr("src", youtube_thumbnail))
		$("#popup-suggestion .middle").html(youtube_title);
		
		// Display updated fancy box
		$.fancybox($("#popup-suggestion"), {
			topRatio: 0.4,
		});

		this.postListen(btn, item);
	}
	else{
		// Suggestion not authorized yet
		this.UIFail(btn)
	}	
}

// Before sending to the server and displaying in the UI, build suggestion item
SuggestionManager.prototype.prePostBuild = function(item, message){
	var channel_id = this.station_client.channel_id;
	var created = PHB.now();
	
	var content = item.content;
	content["key_name"] = channel_id + ".suggested." + created + Math.floor(Math.random()*100).toString()
	content["message"] = message;
	content["created"] = null;
	
	var new_item = this.serverToLocalItem(content);
	
	return new_item;
}

// Listen events relative to posting a suggestion
SuggestionManager.prototype.postListen = function(btn, item){		
	var that = this;
	
	// Textarea typing event limitator
	$("#popup-suggestion textarea").keydown(function(event){
		var message = $("#popup-suggestion textarea").val();
		var neutral_keycodes = [
			8,  //back
			37, //left arrow
			38, //up arrow
			39, //right arrow
			40, //down arrow
			46, //suppr
		]
		
		if(message.length > 139){
			// If the new character is not among the neutral keycodes prevent typing
			if(jQuery.inArray(event.keyCode, neutral_keycodes) == -1){
				event.preventDefault();
			}
		}
	})
	
	// Remove previous binding 
	$("#popup-suggestion form").unbind("submit");
	
	// Listen to submit events
	$("#popup-suggestion form").bind("submit", function(event){
		event.preventDefault()
		
		var message = $("#popup-suggestion textarea").val();
		if(message.length < 10){
			$("#popup-suggestion .warning").show()
		}
		else{		
			// Build the Track item + message into a Suggestion item
			var new_item = that.prePostBuild(item, message)
			
			// Set button as suggested
			that.UISuccess(btn)
			
			// Remove fancy box
			$.fancybox.close(true)
			
			// Reset popup
			$("#popup-suggestion textarea").val("");
			$("#popup-suggestion .warning").hide();
			
			// Prepend the suggestion locally
			var new_item_div = that.UIBuild(new_item)
			that.UIPrepend(new_item_div);
			
			// Prevent any suggestion submission before a 3 minutes period
			that.suggestion_on = false;
			setTimeout(function(){
				that.suggestion_on = true;
			}, 180000)
			
			// POST request to the server
			that.post(new_item, function(response){
				that.postCallback(new_item, response);
			})	
			
			// POST action to facebook
			that.postAction(new_item);
		}
	})
},

SuggestionManager.prototype.UISuccess = function(btn){
	btn.addClass("success")
	btn.html("Suggested")
	
	setTimeout(function(){
		btn.removeClass("success")
		btn.html("Suggest")
	}, 2000)
}

SuggestionManager.prototype.UIFail = function(btn){
	btn.addClass("danger")
	btn.html("Wait")
	
	setTimeout(function(){
		btn.removeClass("danger")
		btn.html("Suggest")
	}, 2000)
}

SuggestionManager.prototype.UIBuild = function(item){	
	var id = item.id;
	var content = item.content;
	var created = PHB.convert(item.created);
	
	var message = content.message;
	
	var track_submitter_url = content.track_submitter_url;
	var track_submitter_name = content.track_submitter_name;
	var track_submitter_picture = "https://graph.facebook.com/" + content.track_submitter_key_name + "/picture?type=square";
	
	var youtube_title = content.youtube_title;
	var youtube_duration = PHB.convertDuration(content.youtube_duration);
	var youtube_thumbnail = "http://i.ytimg.com/vi/" + content.youtube_id + "/default.jpg";
	var preview = "http://www.youtube.com/embed/" + content.youtube_id + "?autoplay=1"
	
	var div = $("<div/>").addClass("wrapper-item").attr("id", id)
	
	div.append(
		$("<img/>")
			.addClass("submitter")
			.attr("src", track_submitter_picture)
			.addClass("tuto")
			.attr("data-original-title", track_submitter_name)
	)
	.append(
		$("<div/>")
			.addClass("content")
			.append(
				$("<p/>")
					.append(
						$("<a/>")
							.attr("href", track_submitter_url)
							.html(track_submitter_name)
					)
					.append(" ")
					.append(message)
			)
	)
	.append(
		$("<div/>")
			.addClass("item")
			.append(
				$("<span/>")
					.addClass("square")
					.append(
						$("<img/>").attr("src", youtube_thumbnail)
					)
			)
			.append(
				$("<div/>")
					.addClass("title")
					.append(
						$("<span/>")
							.addClass("middle")
							.html(youtube_title))
			)
			.append(
				$("<div/>")
					.addClass("subtitle")
					.append(
						$("<div/>")
							.addClass("duration")
							.html(youtube_duration)
					)
			)
	)
	
	if(this.station_client.admin){
		div.find(".subtitle").append(
			$("<div/>")
				.addClass("process-actions")
				.append(
					$("<a/>")
						.addClass("btn")
						.attr("name", id)
						.html("Queue")
						.addClass("tuto")
						.attr("data-original-title", "Add this track to the queue")
				)
				.append(
					$("<a/>")
						.addClass("preview")
						.addClass("fancybox.iframe")
						.attr("href", preview)
						.addClass("tuto")
						.attr("data-original-title", "Preview track")
				)
		)
	}
	
	return div;
}

SuggestionManager.prototype.postAction = function(new_item){
	var track_id = new_item.content.track_id

	// Necessary to have a track id (that means tracks from the listener library)
	if(track_id){
		var track_url = PHB.site_url + "/track/" + track_id;
		var station_url = PHB.site_url + "/" + this.station_client.station.shortname;
		var obj = { "track": track_url };
		var extra = { "station": station_url };
		var expires_in = 0;
		var action = "suggest";	
		FACEBOOK.putAction(action, obj, extra, expires_in);
	}
}

// -------------------------------- NEW --------------------------------------

SuggestionManager.prototype.newEvent = function(){
	// Alert
	this.alert_manager.alert();
}
