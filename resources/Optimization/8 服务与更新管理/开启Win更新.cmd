@echo off
:: Enable and Start Windows Update Service
sc config wuauserv start= auto
sc config wuauserv error= normal
sc start wuauserv

:: Enable and Start Windows Update Orchestra Service
sc config UsoSvc start= auto
sc config UsoSvc error= normal
sc start UsoSvc

echo Services have been enabled and started.
pause
