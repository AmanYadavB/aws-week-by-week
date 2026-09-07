from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def hello():
    return {"msg": "Hello from EC2 - W04 (containerized)", "owner": "Aman"}
