#-*- coding: utf-8 -*-

import re
import urllib2
from bs4 import *
from urlparse import urljoin

#from pysqlite2 import dbapi2 as sqlite
import sqlite3 as sqlite
import nn
mynet=nn.searchnet('nn.db')


# 무시할 단어 목록을 생성함
ignorewords=set(['the','of','to','and','a','in','is','it'])



class crawler:
  # 데이터베이스 이름으로 크롤러를 초기화함
  def __init__(self,dbname):
    self.con=sqlite.connect(dbname)

  def __del__(self):
    self.con.close()

  def dbcommit(self):
    self.con.commit()

  # 항목번호를 얻고 등재되지 않았다면 추가하는 보조 함수
  def getentryid(self,table,field,value,createnew=True):
    cur=self.con.execute(
      "select rowid from %s where %s='%s'" % (table,field,value))
    res=cur.fetchone()
    if res==None:
      cur=self.con.execute(
        "insert into %s (%s) values ('%s')" % (table,field,value))
      return cur.lastrowid
    else:
      return res[0]

  # 개별 페이지를 색인함
  def addtoindex(self,url,soup):
    if self.isindexed(url): return
    print 'Indexing %s' % url
    
    # 개별 단어를 구함
    text=self.gettextonly(soup)
    words=self.separatewords(text)

    # URL id를 구함
    urlid=self.getentryid('urllist','url',url)
    
    # 각 단어를 이 url에 연결함
    for i in range(len(words)):
      word=words[i]
      if word in ignorewords: continue
      wordid=self.getentryid('wordlist','word',word)
      self.con.execute("insert into wordlocation(urlid,wordid,location) \
        values (%d,%d,%d)" % (urlid,wordid,i))

  # HTML 페이지에서 텍스트를 추출함(태그 추출은 안 함)
  def gettextonly(self,soup):
    v=soup.string
    if v==None:
      c=soup.contents
      resulttext=''
      for t in c:
        subtext=self.gettextonly(t)
        resulttext+=subtext+'\n'
      return resulttext
    else:
      return v.strip()

  # 공백문자가 아닌 문자들로 단어들을 분리함
  def separatewords(self,text):
    splitter=re.compile('\\W*')
    return [s.lower() for s in splitter.split(text) if s!='']

  # 이미 색인한 주소라면 true를 리턴
  def isindexed(self,url):
    u=self.con.execute \
       ("select rowid from urllist where url='%s'" % url).fetchone()
    if u!=None:
      # 이미 크롤되었는지 점검함
      v=self.con.execute(
        'select * from wordlocation where urlid=%d' %u[0]).fetchone()
      if v!=None: return True
    return False

  # 두 페이지 간의 링크를 추가
  def addlinkref(self,urlFrom,urlTo,linkText):
    pass

  # 페이지 목록으로 시작해서 넓이 우선 검색을 주어진 깊이만큼 수행함.
  # 그 페이지들을 색인함
  def crawl(self,pages,depth=2):
    pass

  # 데이터베이스 테이블을 생성함
  def createindextables(self):
    self.con.execute('create table urllist(url)')
    self.con.execute('create table wordlist(word)')
    self.con.execute('create table wordlocation(urlid,wordid,location)')
    self.con.execute('create table link(fromid integer, toid integer)')
    self.con.execute('create table linkwords(wordid,linkid)')
    self.con.execute('create index wordidx on wordlist(word)')
    self.con.execute('create index urlidx on urllist(url)')
    self.con.execute('create index wordurlidx on wordlocation(wordid)')
    self.con.execute('create index urltoidx on link(toid)')
    self.con.execute('create index urlfromidx on link(fromid)')
    self.dbcommit()




  def crawl(self,pages,depth=2):
    for i in range(depth):
      newpages=set()
      for page in pages:
        try:
          c=urllib2.urlopen(page)
        except:
          print "Could not open %s" % page
          continue
        soup=BeautifulSoup(c.read())
        self.addtoindex(page,soup)
        links=soup('a')
        for link in links:
          if ('href' in dict(link.attrs)):
            url=urljoin(page,link['href'])
            if url.find("'")!=-1: continue
            url=url.split('#')[0]  # location 부분을 제거함
            if url[0:4]=='http' and not self.isindexed(url):
              newpages.add(url)
            linkText=self.gettextonly(link)
            self.addlinkref(page,url,linkText)

        self.dbcommit()

      pages=newpages


# 페이지랭크 알고리즘

  def calculatepagerank(self,iterations=20):
    # 현 페이지랭크 테이블을 지움
    self.con.execute('drop table if exists pagerank')
    self.con.execute('create table pagerank(urlid primary key,score)')

    # 모든 url의 페이지랭크 값을 1로 초기화함
    self.con.execute('insert into pagerank select rowid, 1.0 from urllist')
    self.dbcommit()

    for i in range(iterations):
      print "Iteration %d" % (i)
      for (urlid,) in self.con.execute('select rowid from urllist'):
        pr=0.15
        
        # 이 페이지에 링크를 가진 모든 페이지들에 대해 루프를 돔
        for (linker,) in self.con.execute(
            'select distinct fromid from link where toid=%d' % urlid):
          # 링크 페이지의 페이지랭크를 얻음
          linkingpr=self.con.execute(
            'select score from pagerank where urlid=%d' % linker).fetchone()[0]
          
          # 링크 페이지의 전체 링크 수를 얻음
          linkingcount=self.con.execute(
            'select count(*) from link where fromid=%' % linker).fetchone()[0]
          pr+=0.85*(linkinpr/linkingcount)
        self.con.execute(
          'update pagerank set score=%f where urlid=%d' % (pr,urlid))
      self.dbcommit()



# 04: 검색하기

class searcher:
  def __init__(self,dbname):
    self.con=sqlite.connect(dbname)

  def __del__(self):
    self.con.close()

  def getmatchrows(self,q):
    # 검색어 생성용 문자열
    fieldlist='w0.urlid'
    tablelist=''
    clauselist=''
    wordids=[]
    
    # 공백으로 단어들을 분리함
    words=q.split(' ')
    tablenumber=0

    for word in words:
      # 단어 ID 구함
      wordrow=self.con.execute(
        "select rowid from wordlist where word='%s'" % word).fetchone()
      if wordrow!=None:
        wordid=wordrow[0]
        wordids.append(wordid)
        if tablenumber>0:
          tablelist+=','
          clauselist+=' and '
          clauselist+='w%d.urlid=w%d.urlid and ' % (tablenumber-1,tablenumber)
        fieldlist+=',w%d.location' % tablenumber
        tablelist+='wordlocation w%d' % tablenumber
        clauselist+='w%d.wordid=%d' % (tablenumber,wordid)
        tablenumber+=1

    # 분리된 단편에서 쿼리를 만듦
    fullquery='select %s from %s where %s' % (fieldlist,tablelist,clauselist)
    cur=self.con.execute(fullquery)
    rows=[row for row in cur]
    
    return rows,wordids



# 05: 내용 기반 랭킹

  def getscoredlist(self,rows,wordids):
    totalscores=dict([(row[0],0) for row in rows])
    
    # 이후 득점 함수를 넣을 위치임
    #weights=[(1.0,self.frequencyscore(rows)),
    #         (1.5,self.locationscore(rows)),
    #         (1.5,self.distancescore(rows))]

    weights=[(1.0,self.locationscore(rows)),
             (1.0,self.frequencyscore(rows)),
             (1.0,self.pagerankscore(rows)),
             (1.0,self.linktextscore(rows,wordids))]

    for (weight,scores) in weights:
      for url in totalscores:
        totalscores[url]+=weight*scores[url]

    return totalscores

  def geturlname(self,id):
    return self.con.execute(
      "select url from urllist where rowid=%d" % id).fetchone()[0]

  def query(self,q):
    rows,wordids=self.getmatchrows(q)
    scores=self.getscoredlist(rows,wordids)
    rankedscores=sorted([(score,url) for (url,score) in scores.items()], reverse=1)
    for (score,urlid) in rankedscores[0:10]:
      print '%f\t%s' % (score,self.geturlname(urlid))
    
    return wordids,[r[1] for r in rankedscores[0:10]]


# 정규화 함수

  def normalizescores(self,scores,smallIsBetter=0):
    vsmall=0.00001 # 영으로 나누는 오류를 피함
    if smallIsBetter:
      minscore=min(scores.values())
      return dict([(u,float(minscore)/max(vsmall,l)) for (u,l) \
                   in scores.items()])
    else:
      maxscore=max(scores.values())
      if maxscore==0: maxscore=vsmall
      return dict([(u,float(c)/maxscore) for (u,c) in scores.items()])


# 단어 빈도

  def frequencyscore(self,rows):
    counts=dict([(row[0],0) for row in rows])
    for row in rows: counts[row[0]]+=1
    return self.normalizescores(counts)


# 문서 내 위치

  def locationscore(self,rows):
    locations=dict([(row[0],1000000) for row in rows])
    for row in rows:
      loc=sum(row[1:])
      if loc<locations[row[0]]: locations[row[0]]=loc

    return self.normalizescores(locations,smallIsBetter=1)


# 단어 거리

  def distancescore(self,rows):
    # 한 단어만 있으면 모두 선택함
    if len(rows[0])<=2: return dict([(row[0],1.0) for row in rows])
    
    # 큰 값들로 딕셔너리를 초기화함
    mindistance=dict([(row[0],1000000) for row in rows])

    for row in rows:
      dist=sum([abs(row[i]-row[i-1]) for i in range(2,len(row))])
      if dist<mindistance[row[0]]: mindistance[row[0]]=dist
    return self.normalizescores(mindistance,smallIsBetter=1)



# 06: 유입 링크 사용하기

# 단순 계산

  def inboundlinkscore(self,rows):
    uniqueurls=set([row[0] for row in rows])
    inboundcount=dict([(u,self.con.execute( \
      'select count(*) from link where toid=%' % u).fetchone()[0]) \
        for u in uniqueurls])
    return self.normalizescores(inboundcount)


# 페이지랭크 알고리즘

  def pagerankscore(self,rows):
    pageranks=dict([(row[0],self.con.execute('select score from pagerank where urlid=%d' % row[0]).fetchone()[0]) for row in rows])
    maxrank=max(pageranks.values())
    normalizedscores=dict([(u,float(l)/maxrank) for (u,l) in pageranks.items()])
    return normalizedscores


# 링크 텍스트 활용

  def linktextscore(self,rows,wordids):
    linkscores=dict([(row[0],0) for row in rows])
    for wordid in wordids:
      cur=self.con.execute('select link.fromid,link.toid from linkwords, link where wordid=%d and linkwords.linkid=link.rowid' % wordid)
      for (fromid,toid) in cur:
        if toid in linkscores:
          pr=self.con.execute('select score from pagerank where urlid=%d' % fromid).fetchone()[0]
          linkscores[toid]+=pr
    maxscore=max(linkscores.values())
    if maxscore != 0:
      normalizedscores=dict([(u,float(l)/maxscore) for (u,l) in linkscores.items()])
      return normalizedscores
    else:
      return linkscores



# 07: 클릭 학습

# 검색엔진에 연결하기

  def nnscore(self,rows,wordids):
    # Get unique URL IDs as an ordered list
    urlids=[urlid for urlid in set([row[0] for row in rows])]
    nnres=mynet.getresult(wordids,urlids)
    scores=dict([(urlids[i],nnres[i]) for i in range(len(urlids))])
    return self.normalizescores(scores)
