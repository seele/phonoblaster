$(function(){
	// Drag and drop 
	var initial_position = null;
	var final_position = null;
	
	$("#buffer-tab .tab-content:nth-child(2)").sortable({
		
		items: ".item:not(:first)",
		zIndex: 4000,
		
		// During sorting
		sort:function(event, ui){
			$(ui.helper).css("borderRight","1px solid #E1E1E1").css("borderLeft","1px solid #E1E1E1")
		},
		
		// Once sorting has stopped
		stop:function(event, ui){
			$(ui.item).css("borderRight","none").css("borderLeft","none")			
		},	
	});
})


// ---------------------------------------------------------------------------
// BUFFER MANAGER
// ---------------------------------------------------------------------------

BufferManager.prototype = new RealtimeTabManager();
BufferManager.prototype.constructor = BufferManager;

function BufferManager(station_client){
	this.init(station_client);
}

//-------------------------------- INIT -----------------------------------

BufferManager.prototype.init = function(station_client){
	RealtimeTabManager.call(this, station_client);
	
	// Settings
	this.url = "/api/buffer"
	this.data_type = "json"
	
	// UI Settings
	this.name = "#buffer-tab";
	this.selector = this.name + " .tab-content:nth-child(2)";
	
	// Additional attributes
	this.live_item = null;
	this.timestamp = null;
	this.history = [];
	this.youtube_manager = new YoutubeManager();
		
	// Init Methods
	this.get();
	this.deleteListen();
}

//--------------------------------- GET -----------------------------------

BufferManager.prototype.get = function(){
	var that = this;	
	var data = this.getData();
	
	// GET items
	$.ajax({
		url: that.url,
		type: "GET",
		dataType: that.data_type,
		timeout: 60000,
		data: data,
		error: function(xhr, status, error) {
			PHB.log('An error occurred: ' + error + '\nPlease retry.');
		},
		success: function(json){
			
			if(json.broadcasts.length > 0){
				that.timestamp = json.timestamp;
				
				that.empty(function(){
					that.getCallback(json.broadcasts);
				})
			}
			else{
				that.noData();
			}

		},
	});
}

BufferManager.prototype.noData = function(){
	// UI modifications
	$("#youtube-player").empty();
	$("#youtube-player").append($("<p/>").html("No live track."));
	$("#media-title").html("No current track.")
	
	if(this.station_client.admin){
		// Open the recommandation manager
	}
}

// Save the intial state of the buffer and trigger the cycle
BufferManager.prototype.getCallback = function(broadcasts){
	
	// Format the list from the server
	for(var i=0, c=broadcasts.length; i<c; i++){
		var new_item = this.serverToLocalItem(broadcasts[i]);
		this.items.push(new_item);
	}

	// Play the new live broadcast
	this.play()
	
	// Display the UI
	this.UIEmpty()
	for(var i=0, c=this.items.length; i<c; i++){
		var item = this.items[i];
		var new_item_div = this.UIBuild(item);
		this.UIAppend(new_item_div);
	}
}

BufferManager.prototype.serverToLocalItem = function(content){
	var item = {
		id: content.client_id,
		content: content
	}
	return item
}

//--------------------------------- INCOMING ---------------------------------------

BufferManager.prototype.add = function(new_event){
	// event = incoming item + information (position, created)
	// state = event + buffer_before + buffer_after
	
	var item = this.serverToLocalItem(new_event.item);
	
	var that = this;
	that.process(new_event, function(buffer_before, buffer_after, previous_item){
		
		var new_state = {
			"event": new_event,
			"buffer_before": buffer_before,
			"buffer_after": buffer_after,
		}
		that.history.push(new_state);
		that.items = buffer_after;
		
		that.UIAdd(item, previous_item);
		
		// In case there is no existing live item
		if(!that.live_item){
			that.timestamp = PHB.now();
			
			that.play();
		}
	})	
}

BufferManager.prototype.remove = function(new_event){
	
	var that = this;
	that.process(new_event, function(buffer_before, buffer_after, previous_item){
		
		var new_state = {
			"event": new_event,
			"buffer_before": buffer_before,
			"buffer_after": buffer_after,
		}
		that.history.push(new_state);
		that.items = buffer_after;
		
		that.UIRemove(new_event.id);
	})
}

BufferManager.prototype.filter = function(new_event, callback){
	
	var created = new_event.created
	var past_states = [];
	var next_events = [new_event];
	
	// Browse history to filter events that happened before and after the new event
	for(var i=0, c=this.history.length; i<c; i++){
		var state = this.history[i];
		var event = state.event;
		
		// Normal case: the new event happened after
		if(event.created <= created){
			past_states.push(state);
		}
		// Unusual case due to PubNub: the new event happened before
		else{
			next_events.push(event);
		}
	}
	
	// Determine which buffer state to build on top of
	var buffer_before = this.items.slice(0);
	// If the past states list is not empty, get the last item buffer
	if(past_states.length > 0){
		buffer_before = past_states[past_states.length-1].buffer_after;
	}
	
	callback(buffer_before, next_events);
}

//BufferManager.prototype.process = function(buffer_before, next_events, callback){
BufferManager.prototype.process = function(new_event, callback){
	
	var that = this;
	// Figure out the right position in the history to insert the event
	this.filter(new_event, function(buffer_before, next_events){
		
		var buffer_after = buffer_before.slice(0);
		var previous_item = null;
		for(var i=0, c=next_events.length; i<c; i++){
			event = next_events[i]

			if(event.id){
				// Remove the item with this id
				for(var j=0, d=buffer_after.length; j<d; j++){
					if(event.id == buffer_after[j].id){
						buffer_after.splice(j,1);
						break;
					}
				}
			}
			else{
				if(event.position){
					// Insert the item in the right position
				}
				else{
					// Add it at the end of the list
					var new_item = that.serverToLocalItem(event.item);
					previous_item = buffer_after[buffer_after.length-1]
					buffer_after.push(new_item);
				}
			}
		}
		
		callback(buffer_before, buffer_after, previous_item)		
	})	
}


//--------------------------------- POST methods -----------------------------------

// Before a track is submitted, we finish building it
BufferManager.prototype.prePostBuild = function(item){
	var channel_id = this.station_client.channel_id;
	var created = PHB.now();

	content = item.content;
	content["client_id"] = channel_id + ".queued." + created + Math.floor(Math.random()*100).toString();
	
	var new_item = this.serverToLocalItem(content)
	return new_item
}
// Submit an item to the buffer (Broadcast a track)
BufferManager.prototype.postSubmit = function(btn, incoming_item){
	var ui_room = this.UIRoom()
	if(ui_room > 0){			
		// Format the Track item into a Broadcast item
		var new_item = this.prePostBuild(incoming_item);
		
		// Display "added" message
		this.UISuccess(btn);
		
		// Append the new item locally
		new_item_div = this.UIBuild(new_item)
		this.UIAppend(new_item_div);
		
		// POST request to the server
		var that = this;
		this.post(new_item, function(response){
			that.postCallback(new_item, response);
		});
	}
	else{
		this.UIFail(btn)
	}
}

BufferManager.prototype.postData = function(item){
	var shortname = this.station_client.station.shortname;		
	var data = {
		shortname: shortname,
		track: JSON.stringify(item.content),
	}
	return data
},

//------------------------------------- UI  -----------------------------------------

// Returns the current live item 
BufferManager.prototype.UILive = function(){
	var item_id = $("#media-id").html();
	return item_id;
}

BufferManager.prototype.UISuccess = function(btn){
	btn.addClass("success")
	btn.html("Added")
	
	setTimeout(function(){
		btn.removeClass("success")
		btn.html("Add")
	}, 2000)
}

BufferManager.prototype.UIFail = function(btn){
	btn.addClass("danger")
	btn.html("Full")
	
	setTimeout(function(){
		btn.removeClass("danger")
		btn.html("Add")
	}, 2000)
},

BufferManager.prototype.UIAdd = function(new_item, previous_item){
	// If the item was initially displayed, we don't care (honey badger style) and remove it
	this.UIRemove(new_item.id);
	var new_item_div = this.UIBuild(new_item);		
		
	if(previous_item){
		// If there was a previous item, we insert the new item just before
		var re = RegExp("[.]","g");
		var previous_item_selector = this.selector + " #" + previous_item.id.replace(re, "\\.");
		this.UIInsert(new_item_div, previous_item_selector)
	}
	else{
		// Else, we have to append the item at the top of the column
		this.UIPrepend(new_item_div); // Specific to the BufferManager
	}
}

BufferManager.prototype.UIBuild = function(item){
	var id = item.id;
	var content = item.content;
	var type = content.type;
	
	var youtube_id = content.youtube_id;
	var youtube_title = content.youtube_title;
	var youtube_duration = PHB.convertDuration(content.youtube_duration)
	var youtube_thumbnail = "https://i.ytimg.com/vi/" + youtube_id + "/default.jpg";
	
	var track_submitter_name = content.track_submitter_name;
	var track_submitter_url = content.track_submitter_url;
	var track_submitter_picture = "https://graph.facebook.com/" + content.track_submitter_key_name + "/picture?type=square";	
	
	var mention = null;
	if(type == "suggestion"){
		mention = "Suggested by"
	}
	if(type == "favorite"){
		mention = "Rebroadcast of"
	}
	
	var div = $("<div/>").addClass("item").attr("id", id)
	
	div.append(
		$("<div/>")
			.addClass("item-picture")
			.append($("<img/>").attr("src", youtube_thumbnail))
	)
	.append(
		$("<div/>")
			.addClass("item-title")
			.append($("<span/>").addClass("middle").html(youtube_title))
	)
	
	if(this.station_client.admin){
		div.append(
			$("<a/>")
				.attr("href","#")
				.addClass("item-cross")
				.attr("name", id)
				.html("X")
		)
	}
	
	div.append(
		$("<div/>")
			.addClass("item-subtitle")
			.append($("<div/>").addClass("item-duration").html(youtube_duration))
	)
	
	
	if(mention){
		var subtitle = div.find(".item-subtitle")
		subtitle.append(
			$("<div/>")
				.addClass("item-submitter")
				.append(
					$("<a/>")
						.attr("href", track_submitter_url)
						.attr("target", "_top")
						.append(
							$("<img/>")
								.attr("src", track_submitter_picture)
								.addClass("tuto")
								.attr("data-original-title", track_submitter_name)
						)
				)
				.append($("<span/>").html(mention))
		)
	}
	
	return div
}

BufferManager.prototype.UIInsert = function(new_item_div, previous_item_selector){	
	new_item_div.insertAfter(previous_item_selector); // Specific to the BufferManager
}

BufferManager.prototype.UIEmpty = function(){
	var that = this;
	$(that.selector).empty();
}

BufferManager.prototype.UIRoom = function(){

	var room = 30;
	if(this.UILive()){
		var items_selector = this.selector + " .item"
		var items_number = $(items_selector).length
		room = 29 - items_number;
	}
	
	return room
}

//------------------------------------- LIVE -----------------------------------------

BufferManager.prototype.getBufferDuration = function(){
	var total_duration = 0;
	for(var i=0, c=this.items.length; i<c; i++){
		total_duration += this.items[i].content.youtube_duration;
	}
	return total_duration;
}

// Play the new live broadcast
BufferManager.prototype.play = function(){
	var buffer_duration = this.getBufferDuration();
	var offset = ((PHB.now() - this.timestamp)) % buffer_duration
	var before = 0;
	var start = 0;
	var timeout = 0;
	
	var new_live_item = null;
	var ordered_buffer = [];
	
	for(var i=0, c=this.items.length; i<c; i++){
		var item = this.items[i];
		var duration = item.content.youtube_duration;
		
		// This is the current track 
		if(before + duration > offset){
			start = offset - before;
			timeout = duration - start;
					
			var previous_items = this.items.slice(0,i);
			var new_live_item = this.items[i];
			var next_items = this.items.slice(i+1);
			
			var ordered_buffer = [new_live_item].concat(next_items, previous_items);
			break;
		}
		// We must keep browsing the list before finding the current track
		else{
			before += duration
		}
	}
	
	// Update data
	this.live_item = new_live_item
	this.items = ordered_buffer
	this.timestamp = PHB.now() - start;
	
	// Play the live broadcast
	this.youtube_manager.init(new_live_item, start);
	
	// Program the next play
	var that = this;
	setTimeout(function(){
		// Refresh the UI
		that.UIRefresh()

		// Trigger the next broadcast
		that.play()
				
	}, timeout * 1000);
}

BufferManager.prototype.UIRefresh = function(){
	var item_div = this.UIBuild(this.live_item);
	
	// Remove old live item from the top
	this.UIRemove(this.live_item.id)
	
	// Replace old live item at the bottom
	this.UIAppend(item_div)
}