gsk_poc


接口1：
POST /create_session
```sh

curl -X POST http://127.0.0.1:8000/create_session

# 返回值
{"session_id":"6febef12f52a11efbfed0242ac120006","status":"success","message":"Session created successfully"}
```


接口4：
POST /chat_on_docs/{session_id}
```sh
#会话有文档
curl -X POST http://127.0.0.1:8000/chat_on_docs/6febef12f52a11efbfed0242ac120006 \
     -H "Content-Type: application/json" \
     -d '{"message": "世运电路成长性怎么样"}' \
     -i

```
gsk-poc:fb0820ca-5e4d-401c-ab8e-a7b54e13a630


查询数据：
```sh
curl -X GET "http://127.0.0.1:8000/get_chat_data?key=gsk-poc:fb0820ca-5e4d-401c-ab8e-a7b54e13a630"

```



