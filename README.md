PS C:\Users\User\Desktop\VANTA\Vanta-main>  python vanta_ui/server.py

=======================================================
  VANTA v4 — Natural Intelligence Mode
  http://localhost:5000
  RAG: ✓  Google: ✓  Orch: ✓  Watcher: ✓
=======================================================

✅  Watcher daemon started — 1 project(s), 0 news feed(s)
 * Serving Flask app 'server'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
Traceback (most recent call last):
  File "C:\Users\User\Desktop\VANTA\Vanta-main\vanta_ui\server.py", line 1209, in <module>
    socketio.run(app, host="127.0.0.1", port=port, debug=False)
  File "C:\Python314\Lib\site-packages\flask_socketio\__init__.py", line 674, in run
    app.run(host=host, port=port, threaded=True,
  File "C:\Python314\Lib\site-packages\flask\app.py", line 662, in run
    run_simple(t.cast(str, host), port, self, **options)
  File "C:\Python314\Lib\site-packages\werkzeug\serving.py", line 1126, in run_simple
    srv.serve_forever()
  File "C:\Python314\Lib\site-packages\werkzeug\serving.py", line 824, in serve_forever
    self.server_close()
  File "C:\Python314\Lib\socketserver.py", line 714, in server_close
    super().server_close()
  File "C:\Python314\Lib\socketserver.py", line 489, in server_close
    def server_close(self):
KeyboardInterrupt
