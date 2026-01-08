import webview

class Api:
	def do_something(self):
		print("did something")

api=Api()

webview.create_window(
	"Wareneingang B7",
	url="public/index.html",
	fullscreen=True,
	js_api=api
)

webview.start()
