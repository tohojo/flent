// Include this file along with the dash.js player to enable logging
// The log output will be parsed by Flent
var player;
var tmp_date;
var starttime;
var off = 1;
var stoptime;
var stalling=0;
var first_log = 1;
var log_base;

function time_log(Type,D1,D2,D3) {
	var tmp_d = new Date();
	if (first_log) {
		log_base = tmp_d.getTime();
		first_log = 0;
	}
	var t_stamp = tmp_d.getTime() - log_base;
	// D,time,type,d1,d2,d3
	console.log("D," + t_stamp + "," + Type + "," + D1 + "," + D2 + "," + D3);
}

function showEvent(e) {
	// we can now play, either after initial loading or stalling
	if (e.type == "canPlay") {
		if (off) {
			off = 0;
			tmp_date = new Date();
			var start_elapsed = tmp_date.getTime() - starttime;
			var q_idx = player.getQualityFor('video');
			var q_obj = player.getBitrateInfoListFor('video')[q_idx];
			var bitrate = q_obj.bitrate;

			time_log("ID",start_elapsed,null,null);
			time_log("IR",bitrate,null,null);
		} else {
			if (stalling) {
				tmp_date = new Date();
				var stop_elapsed = tmp_date.getTime() - stoptime;
				time_log("SD",stop_elapsed,null,null);
				stalling=0;
			}
		}

	}
	// we have now run out of buffer space, begin stall period
	if (e.type == "bufferStalled" && e.mediaType == "video") {
		stalling=1;
		stoptime = new Date();
	}
	// we have a quality change!
	if (e.type == "qualityChangeRequested" && e.mediaType == "video") {
		var q_idx = player.getQualityFor('video');
		var q_obj = player.getBitrateInfoListFor('video')[q_idx];
		if (e.reason != undefined)
			time_log("QC",e.oldQuality,e.newQuality,e.reason.name);
		else
			time_log("QC",e.oldQuality,e.newQuality,null);

		time_log("BC",q_obj.bitrate);

	}


	if (e.type == "playbackProgress") {
		time_log("AT", player.getAverageThroughput('video'),null,null);
		time_log("BL", player.getBufferLength('video')*1000,null,null);
	}


	if (e.type == "fragmentLoadingCompleted" && e.request.mediaType == 'video') {
		let now = new Date().getTime();
		time_log("FC",(now-e.request.delayLoadingTime),null,null);
	}
}


function init()
{
	player = dashjs.MediaPlayerFactory.create(document.querySelector(".dashjs-player"));
	player.getDebug().setLogTimestampVisible(true);
	player.getDebug().setLogToBrowserConsole(false);

	// save start time
	tmp_date = new Date();
	starttime = tmp_date.getTime();

	// events to listen for
	player.on(dashjs.MediaPlayer.events["CAN_PLAY"], showEvent);
	player.on(dashjs.MediaPlayer.events["BUFFER_EMPTY"], showEvent);
	player.on(dashjs.MediaPlayer.events["QUALITY_CHANGE_REQUESTED"], showEvent);
	player.on(dashjs.MediaPlayer.events["FRAGMENT_LOADING_COMPLETED"], showEvent);
	player.on(dashjs.MediaPlayer.events["PLAYBACK_PROGRESS"], showEvent);
}

