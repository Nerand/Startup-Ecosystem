"""Подбор и маршруты."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import argparse, json, sqlite3, uuid, datetime, mimetypes, os

ROOT=Path(__file__).resolve().parent
CATALOG=json.loads((ROOT/'catalog.json').read_text())
TOPICS={'programming','ai','engineering','science'}

def profile(data):
    if not isinstance(data,dict): raise ValueError('Ожидается объект с параметрами проекта')
    result={k:data.get(k) for k in ('title','grade','age','team','topics','has_project')}
    if not isinstance(result['title'],str) or not 1<=len(result['title'].strip())<=120: raise ValueError('Название: от 1 до 120 символов')
    result['title']=result['title'].strip()
    for field,low,high in [('grade',5,11),('age',10,21),('team',1,20)]:
        if type(result[field]) is not int or not low<=result[field]<=high: raise ValueError(f'Некорректное поле: {field}')
    if not isinstance(result['topics'],list) or not result['topics'] or any(t not in TOPICS for t in result['topics']): raise ValueError('Выберите направление из списка')
    if type(result['has_project']) is not bool: raise ValueError('Укажите готовность проекта')
    return result

def evaluate(p,e):
    reasons=[]; blocks=[]
    (reasons if e['min_grade']<=p['grade']<=e['max_grade'] else blocks).append(f"Классы: {e['min_grade']}–{e['max_grade']}")
    if e['min_age'] is not None:
        (reasons if e['min_age']<=p['age']<=e['max_age'] else blocks).append(f"Возраст: {e['min_age']}–{e['max_age']} лет")
    if e['max_team'] is not None:
        (reasons if p['team']<=e['max_team'] else blocks).append(f"Не более {e['max_team']} авторов")
    if e['needs_project']:
        (reasons if p['has_project'] else blocks).append('Нужна собственная исследовательская работа')
    overlap=sorted(set(p['topics'])&set(e['topics']))
    if not overlap: blocks.append('Не совпало выбранное направление')
    else: reasons.append('Совпало направление по редакционным меткам')
    return dict(event=e,eligible=not blocks,reasons=reasons,blocks=blocks,matched_topics=overlap)

def connect(path):
    c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c

def initialize(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with connect(path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS routes(id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

def route_create(path,p,event_id,target):
    e=next((e for e in CATALOG if e['id']==event_id),None)
    if e is None: raise ValueError('Неизвестное мероприятие')
    if not evaluate(p,e)['eligible']: raise ValueError('Параметры не соответствуют сохранённым условиям')
    try: date=datetime.date.fromisoformat(target)
    except (TypeError,ValueError): raise ValueError('Укажите дату внутренней готовности')
    if date<datetime.date.today(): raise ValueError('Дата готовности не может быть в прошлом')
    route={'id':uuid.uuid4().hex,'project':p,'event':e,'target':date.isoformat(),'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tasks':[{'id':str(i),'title':t,'done':False,'due':(date-datetime.timedelta(days=(len(e['tasks'])-1-i)*2)).isoformat()} for i,t in enumerate(e['tasks'])]}
    with connect(path) as c: c.execute('INSERT INTO routes VALUES (?,?)',(route['id'],json.dumps(route,ensure_ascii=False)))
    return route

def routes(path):
    with connect(path) as c: return [json.loads(r['payload']) for r in c.execute('SELECT payload FROM routes ORDER BY rowid DESC')]

def toggle(path,rid,tid,done):
    if type(done) is not bool: raise ValueError('Статус должен быть true или false')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        record=c.execute('SELECT payload FROM routes WHERE id=?',(rid,)).fetchone()
        if record is None: raise ValueError('Маршрут не найден')
        route=json.loads(record['payload']); task=next((t for t in route['tasks'] if t['id']==tid),None)
        if task is None: raise ValueError('Действие не найдено')
        task['done']=done
        c.execute('UPDATE routes SET payload=? WHERE id=?',(json.dumps(route,ensure_ascii=False),rid))
    return route

def make_server(port=8088,db=None):
    db=db or str(ROOT/'data/routes.db'); initialize(db)
    class Handler(BaseHTTPRequestHandler):
        def send_json(self,obj,status=200):
            body=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/api/events': return self.send_json(CATALOG)
            if path=='/api/routes': return self.send_json(routes(db))
            if path=='/api/health': return self.send_json({'ok':True})
            files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in files: return self.send_json({'error':'Не найдено'},404)
            file=ROOT/'static'/files[path]; data=file.read_bytes(); self.send_response(200)
            self.send_header('Content-Type',mimetypes.guess_type(file)[0]+'; charset=utf-8'); self.send_header('Content-Length',str(len(data)))
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}': return self.send_json({'error':'Чужой источник запроса'},403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=50000: raise ValueError('Размер запроса должен быть от 1 до 50000 байт')
                data=json.loads(self.rfile.read(size)); path=urlparse(self.path).path
                if path=='/api/match': return self.send_json([evaluate(profile(data),e) for e in CATALOG])
                if path=='/api/routes': return self.send_json(route_create(db,profile(data['profile']),data['event_id'],data['target']),201)
                parts=path.strip('/').split('/')
                if len(parts)==5 and parts[:2]==['api','routes'] and parts[3]=='tasks': return self.send_json(toggle(db,parts[2],parts[4],data['done']))
                return self.send_json({'error':'Не найдено'},404)
            except (ValueError,KeyError,TypeError) as error: return self.send_json({'error':str(error)},400)
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8088); parser.add_argument('--db'); args=parser.parse_args()
    server=make_server(args.port,args.db); print(f'Конкурсный маршрут: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
