$('input[name="clustering"]').change(function() {
  var value = $(this).filter(':checked').val();
  $('._clustering-options').toggle(value == 'manual');
});
$('._clustering-options').hide();


// Note that the path doesn't matter right now; any WebSocket
// connection gets bumped over to WebSocket consumers
socket = new WebSocket("ws://" + window.location.host + "/chat/");
socket.onmessage = function(e) {
    alert(e.data);
}
socket.onopen = function() {
    socket.send("hello world");
}
// Call onopen directly if socket is already open
if (socket.readyState == WebSocket.OPEN) socket.onopen();