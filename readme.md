[seamk_logo]:   /img/seamk_logo.svg
[ely_logo]:     /img/elyfi-logo.png
[euo_logo]:     /img/euo-logo.png 
[agrop_logo]:   /img/agropilotti-logo.png
[grafana]:      /img/grafana.jpg

![agrop_logo]

# Tukiaseman status

## RTK tukiasema

RTK (real-time kinematic positioning) auttaa parantamaan paikannustarkkuutta senttimetri tasolle tarjoamalla korjaussignaalin tarkkasti paikannetusta tukiasemasta liikkuvalla kohteelle. Tämän korjaussignaalin avulla voidaan suodattaa pois ilmakehän häiriöitä jne. 

Hankkeen työpajoissa rakennettiin 30 RTK-tukiasemaa Etelä-Pohjanmaan alueelle. Näistä suurin on kytketty ilmaiseksi käytettävään RTK2Go-palveluun, minkä kautta niitä voivat hyödyntää kaikki sopivalla etäisyydellä olevat tarvitsijat. 

Tukiasemat pyörivät Raspberry Pi:ssä olevan [rtkbase](https://github.com/Stefal/rtkbase) ohjelman ympärillä. rtkbase on helppo asenteinen kokonaisuus mikä kerää yhteen oman RTK-tukiaseman pyörittämiseen tarvittavat ohjelmat ja lisää päälle webbikäyttöliittymän millä kokonaisuutta hallitaan.

## Toiminnan kuvaus

`poll.py` python scripti on yksinkertainen, säännöllisin väliajoin ajattevaksi suunniteltu tiedonkerääjä, joka hakee dataa eri lähteistä tukiaseman sisällä ja muotoilee ne tallennettavaksi timeseries-tietokantaan.

## Datan keruu

### Lämpötilat

Scripti lukee `/sys` hakemistosta CPUn lämpötilan. Joissain tilanteissa tukiaseman kotelo on asennettu kuivaajan tms. rakennuksen kattorakenteisiin, paremman antennin sijoittelun takia, ja näissä paikoissa voi ympäristön lämpötilan kohota suht korkeaksi. 

Kokeen vuoksi esimerkissä on myös onewire-lämpötila-anturien lukeminen. Näitä halpoja DS18B20 antureita voi liittää Raspberryyn useampiakin ja siten seurata esimerkiksi kotelon sisäistä lämpötilaa ja asennustilan lämpötilaa. Ja jos lähistöllä on jotain muutakin kiinnostavaa, voi tämä toimia keskitettynä lämpötilojen kerääjänä. 

Ohjeita kuinka onewire-anturit saa toimimaan, löytyy verkosta useita, [tässä yksi](https://randomnerdtutorials.com/raspberry-pi-ds18b20-python/).

### gpsd

[gpsd](https://gpsd.io/) on tausta-ohjelma, joka juttelee gps-vastaanottimen kanssa. Tämä scripti ottaa siihen yhteyden ja pyytää tietoja tämän hetkisestä sijainnista sekä siitä mitä satelliitteja nyt näkyy. Tämä tapahtuu paikallisen socket-yhteyden yli.

## Tallennus

Scripti on suunniteltu käytettäväksi [influxdb](https://www.influxdata.com/products/influxdb/) v2:n kanssa. Kerätty data muotoillaan sopivaksi yhteen datapisteeseen, joka tallennetaan kantaan. Huom. yksittäisten satelliittien data menee omina pisteinään, jotta niitä olisi helpompi erikseen seurata.

## Visualisointi

![grafana]

Visualisoinnin rakentamista ei tässä tarkemmin käsitellä, sen voi toteuttaa monella haluamallaan tavalla. Yllä on kuvakaappaus [Grafanaan](https://grafana.com/grafana/) tehdystä dashboardista, mutta mahdollista on käyttää muitakin työkaluja, jotka osaavat lukea datan influxdb kannasta, kuten influxin oma [sisäänrakennettu visualisointi](https://docs.influxdata.com/influxdb/v2/get-started/visualize/) tai [Home Assistant[(https://docs.influxdata.com/influxdb/v2/get-started/visualize/) 

## Asennus

Oletuksena on, että sinulla on toimiva, Raspberry Pin päällä pyörivä tukiasema ja asennat tämän scriptin samalla koneelle. Influxdb on myös asennettuna ja siihen saa yhteyden tukiasemasta.

Luo ensin tarvittaessa influxdb:ssä [oma bucket](https://docs.influxdata.com/influxdb/cloud/admin/buckets/) tukiaseman tiedoille sekä [luo token](https://docs.influxdata.com/influxdb/cloud/admin/tokens/) jota käytetään yhteyden muodostamiseen ja ota sen talteen. 

Kun olet kloonannut repositoryn omaan hakemistoonsa. Tee ensin sille oma python virtuaaliympäristö ja aktivoi se.

```
$ python -m venv .venv
$ source .venv/bin/activate
```

Asenna tämän jälkeen tarvittavat paketit.
```
$ pip install --upgrade pip wheel
$ pip install -r requirements.txt
```

Luo konffaustiedosto sample.ini:n pohjalta ja päivitä siihen influxdb:n osoite, token, org ja bucket sekä listaa onewire anturit omaan osioonsa. Koska niiden id alkaa nollalla, ne on prefixattu `id_` tässä tiedostossa. Jos et tiedä mikä anturin id on, se löytyy `/sys/bus/w1/devices` hakemistosta, missä ne ovat `28-` prefixillä. 

```
$ ls /sys/bus/w1/devices/
28-0000001e062e  28-173e550a6461  w1_bus_master1
```

Tai kun olet asentanut requirementsit, voit ajaa myös mukana tulleen apuohjelman, joka listaa löytyneet anturit.

```
$ w1thermsensor ls
Found 2 sensors:
  1. HWID: 173e550a6461 Type: DS18B20
  2. HWID: 0000001e062e Type: DS18B20
```

Scripti ei itse lataa kernel moduleja kuten joissain esimerkeissä tehdään. Koska tämä on suht pysyväksi suunniteltu ohjelma, lisäsin ne suoraan `/etc/modules-load.d/modules` tiedoston listalle.
```
$ cat /etc/modules-load.d/modules.conf
# /etc/modules: kernel modules to load at boot time.
#
# This file contains the names of kernel modules that should be loaded
# at boot time, one per line. Lines beginning with "#" are ignored.
# Parameters can be specified after the module name.

w1-gpio
w1-therm
```

Nyt voit koittaa ajaa scriptin, se ei tarvitse muuta kuin ini-tiedoston sijainnin parametrikseen. Jos mitään ei tulostu, niin ajo meni onnituneesti läpi ja influxdb:ssä pitäisi näkyä uusi datapiste.

```
$ python poll.py poll.ini
```

Jotta dataa olisi enemmän ihmeteltävänä, scriptiä pitää ajaa useammin. Yksinkertaisin tapa on lisätä sen crontabiin (`crontab -e`) ja antaa sen ajastaa ajot. Alla esimerkki, joka käynnistää tämän viiden minuutin välein ja kirjaa mahdolliset virheet omaan logi tiedostoon. Alla olevassa esimerkissä scripti on asennettu "status" nimiseen hakemistoon seamk-nimisen käyttäjän kotihakemistoon.

```
# m h  dom mon dow   command
*/5	*	*	*	*	/home/seamk/status/venv/bin/python /home/seamk/status/poll.py /home/seamk/status/poll.ini >> /home/seamk/status/poll.log 2>&1
```

## Agropilotti

Tämä ohjelma luotiin osana Agropilotti hanketta, jossa rakennettiin ja esiteltiin tee-se-itse mahdollisuuksia työkoneiden automaattiohjaukseen. 

---

![euo_logo]

---

![ely_logo]

---

![seamk_logo]
