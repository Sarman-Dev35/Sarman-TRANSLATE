from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from collections import Counter
from PySide6.QtCore import QObject, QUrl, QUrlQuery, Signal, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QFont
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

WARM_PALETTE=("#f06a3d","#a92f45")
_GAME_PALETTES={
 "adofai":("#f04459","#397ee8"),
 "a dance of fire and ice":("#f04459","#397ee8"),
 "geometry dash":("#3988ef","#f3c744"),
 "geometrydash":("#3988ef","#f3c744"),
}
def palette_for_game(name):
 key=" ".join(str(name).casefold().replace("_"," ").replace("-"," ").split())
 for token,palette in _GAME_PALETTES.items():
  if token in key or key in token:return palette
 return WARM_PALETTE

def _hex(rgb):return "#{:02x}{:02x}{:02x}".format(*rgb)
def dominant_palette(image):
 if image.isNull():return WARM_PALETTE
 sample=image.scaled(48,48); buckets=Counter(); reps={}
 for y in range(sample.height()):
  for x in range(sample.width()):
   c=sample.pixelColor(x,y); h,s,v,_=c.getHsv()
   if h<0 or s<85 or v<65:continue
   bucket=int(h/18)%20; buckets[bucket]+=1
   reps.setdefault(bucket,(c.red(),c.green(),c.blue()))
 if not buckets:return WARM_PALETTE
 top=[b for b,_ in buckets.most_common(5)]; first=reps[top[0]]
 second=next((reps[b] for b in top[1:] if min(abs((b-top[0])%20),abs((top[0]-b)%20))>=3),None)
 if second is None:second=(first[2],first[0],first[1])
 return _hex(first),_hex(second)

def _mix(left,right,t):
 a,b=QColor(left),QColor(right); t=max(0.0,min(1.0,float(t)))
 return _hex((round(a.red()*(1-t)+b.red()*t),round(a.green()*(1-t)+b.green()*t),round(a.blue()*(1-t)+b.blue()*t)))
def interpolate_palette(start,end,t):return _mix(start[0],end[0],t),_mix(start[1],end[1],t)

def theme_stylesheet(accent="#f06a3d",secondary="#a92f45",compact=False):
 radius="10px" if compact else "12px"
 return f"""
 QWidget{{background:#0b0d12;color:#f2f0ed;font-family:'Segoe UI';font-size:13px;}}
 QFrame#sidebar{{background:#10131a;border-right:1px solid #252a34;}}
 QLabel#brand{{font-size:24px;font-weight:900;letter-spacing:2px;color:#fffaf5;}}
 QLabel#brandSub,QLabel#eyebrow{{color:{accent};font-size:10px;font-weight:850;letter-spacing:1.8px;}}
 QLabel#sideFoot,QLabel#muted{{color:#8e95a3;}}
 QLabel#pageTitle{{font-size:25px;font-weight:800;}}
 QLabel#sectionTitle{{font-size:17px;font-weight:750;}}
 QLabel#heroTitle{{font-size:25px;font-weight:850;}}
 QFrame#hero{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1b202b,stop:0.58 #151923,stop:1 #21171b);border:1px solid {accent};border-radius:16px;}}
 QFrame#panel,QFrame#statCard{{background:#141923;border:1px solid #2b303c;border-radius:{radius};}}
 QPushButton{{background:#191e28;border:1px solid #343b49;border-radius:{radius};padding:10px 14px;font-weight:700;}}
 QPushButton:hover{{border-color:{accent};background:#25202a;}}
 QPushButton:disabled{{color:#626b79;background:#171b23;border-color:#292f3a;}}
 QPushButton#primary{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {accent},stop:1 {secondary});color:#fff;border:0;padding:11px 17px;font-weight:900;}}
 QPushButton#navButton,QPushButton#navActive{{text-align:left;padding:13px 12px;border:0;}}
 QPushButton#navButton{{background:transparent;color:#a5adba;}}
 QPushButton#navActive{{background:{accent}22;color:#fff;border-left:3px solid {accent};}}
 QLineEdit{{background:#141923;border:1px solid #343b49;border-radius:{radius};padding:10px 12px;color:#fff;}}
 QLineEdit:focus{{border-color:{accent};}}
 QTableWidget{{background:#10151e;alternate-background-color:#141a24;border:1px solid #2b303c;border-radius:14px;padding:5px;selection-background-color:{accent}44;gridline-color:transparent;}}
 QHeaderView::section{{background:#171d28;color:{accent};border:0;padding:12px 9px;font-size:10px;font-weight:900;letter-spacing:1px;}}
 QTableWidget::item{{padding:9px 8px;border-bottom:1px solid #242b37;}}
 QTableWidget::item:selected{{background:{accent}30;color:#fff;}}
 QLabel#warning{{color:#f0bd91;background:#251a1b;border:1px solid {secondary};border-radius:10px;padding:12px;}}
 QComboBox{{background:#141923;border:1px solid #343b49;border-radius:{radius};padding:8px 10px;min-width:150px;}}
 QComboBox::drop-down{{border:0;width:25px;}}
 QComboBox QAbstractItemView{{background:#171d28;selection-background-color:{accent}55;}}
 QProgressBar{{background:#171d28;color:#f5f1ed;border:1px solid #303746;border-radius:7px;text-align:center;min-height:12px;}}
 QProgressBar::chunk{{border-radius:6px;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {accent},stop:1 {secondary});}}
 QScrollBar:vertical{{background:#10151e;width:10px;margin:2px;}}
 QScrollBar::handle:vertical{{background:#394252;border-radius:5px;min-height:28px;}}
 """

def make_placeholder_cover(name,platform,accent,secondary,size=(220,124)):
 image=QImage(size[0],size[1],QImage.Format_ARGB32_Premultiplied); image.fill(QColor("#10141d"))
 p=QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
 g=QLinearGradient(0,0,size[0],size[1]);g.setColorAt(0,QColor(accent));g.setColorAt(1,QColor(secondary))
 p.setBrush(g);p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(0,0,size[0],size[1],13,13)
 p.setPen(QColor(255,255,255,36))
 for off in range(-size[1],size[0],28):p.drawLine(off,0,off+size[1],size[1])
 p.setPen(QColor("#ffffff"));f=QFont("Segoe UI",15);f.setBold(True);p.setFont(f)
 p.drawText(15,18,size[0]-30,55,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,str(name)[:26])
 f=QFont("Segoe UI",8);f.setBold(True);p.setFont(f);p.setPen(QColor(255,255,255,190))
 p.drawText(15,size[1]-24,size[0]-30,16,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,str(platform).upper()[:34])
 p.end();return image

class GameArtService(QObject):
 cover_ready=Signal(str,object,str,str)
 def __init__(self,parent=None):
  super().__init__(parent);self.manager=QNetworkAccessManager(self)
  self.cache_dir=Path(os.environ.get("LOCALAPPDATA",Path.home()))/"Sarman"/"TRANSLATE"/"covers"
  self.pending={};self.requested=set()
 @staticmethod
 def _key(path):return hashlib.sha256(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:24]
 def request(self,game):
  path=str(game.path)
  if path in self.requested:return
  self.requested.add(path);cache=self.cache_dir/(self._key(path)+".jpg")
  if cache.is_file():
   image=QImage(str(cache))
   if not image.isNull():QTimer.singleShot(0,lambda p=path,i=image:self._emit(p,i));return
  appid=str(getattr(game,"app_id","") or "").strip()
  if appid.isdigit():self._download(path,f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg")
  else:
   url=QUrl("https://store.steampowered.com/api/storesearch/");q=QUrlQuery()
   q.addQueryItem("term",str(game.name)[:100]);q.addQueryItem("l","english");q.addQueryItem("cc","us");url.setQuery(q)
   self._send(path,"search",url.toString())
 def _send(self,path,phase,url):
  req=QNetworkRequest(QUrl(url));req.setRawHeader(b"User-Agent",b"Sarman-TRANSLATE/1.0")
  reply=self.manager.get(req);self.pending[reply]=(path,phase);reply.finished.connect(lambda r=reply:self._finished(r))
 def _download(self,path,url):self._send(path,"image",url)
 def _finished(self,reply):
  path,phase=self.pending.pop(reply,("",""))
  try:
   if reply.error():return
   data=bytes(reply.readAll())
   if phase=="search":
    items=json.loads(data.decode("utf-8")).get("items") or []
    if items:
     url=str(items[0].get("header_image") or "")
     if url.startswith("https://"):self._download(path,url)
    return
   image=QImage.fromData(data)
   if image.isNull() or image.width()<100 or image.height()<50:return
   self.cache_dir.mkdir(parents=True,exist_ok=True);image.save(str(self.cache_dir/(self._key(path)+".jpg")),"JPG",88)
   self._emit(path,image)
  except (ValueError,OSError,TypeError,KeyError):pass
  finally:reply.deleteLater()
 def _emit(self,path,image):
  a,b=dominant_palette(image);self.cover_ready.emit(path,image,a,b)
