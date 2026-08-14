@echo off
:: Stop and Disable Windows Update Service
sc stop wuauserv
sc config wuauserv start= disabled
sc config wuauserv error= ignore

:: Stop and Disable Windows Update Orchestra Service
sc stop UsoSvc
sc config UsoSvc start= disabled
sc config UsoSvc error= ignore

echo Services have been stopped and disabled.
pause
