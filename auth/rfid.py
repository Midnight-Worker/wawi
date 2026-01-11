from smartcard.System import readers

r = readers()
print("Reader:", r)

connection = r[0].createConnection()
connection.connect()

print("ATR:", connection.getATR())

