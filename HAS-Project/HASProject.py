import sys,os,threading,shutil,subprocess,platform,csv,cv2,time
from tkinter import filedialog,messagebox
from PIL import Image
import customtkinter as ctk
import pyaudio,wave

# ---------- Kamera/Ses Kontrol ----------
capture = None
cameraActive = False
lastWarning = 0
manualRecord = False
activeTasks = 0
audioFrames = []
audioStream = None
audioPyAudio = None
isAudioRecord = False
micActive = False
audioChannels = 2
audioRate = 24000
manualRecBTN = None

# ---------- Güvenli Çıkış Protokolü ----------
def _OnAppClose():
    global cameraActive, activeTasks
    cameraActive = False

    if activeTasks > 0:
        waitWindow = ctk.CTkToplevel(window)
        waitWindow.title("Sistem Kapanıyor...")
        waitWindow.geometry("400x150")
        waitWindow.attributes("-topmost", True)

        ctk.CTkLabel(
            waitWindow,
            text="Arka planda video işleniyor!\nLütfen güvenle kapanmasını bekleyin...",
            font=("Segoe UI", 16, "bold"),
            text_color="#f1c04f").pack(expand=True)
        waitWindow.update()
        while activeTasks > 0:
            time.sleep(0.5)
            waitWindow.update()
    window.destroy()
    sys.exit(0)

# ---------- Mikrafon Girdi Fonksiyonu ----------
def _StartAudio(filename):
    global audioStream,audioPyAudio,audioFrames,isAudioRecord,micActive,audioChannels,audioRate

    devnull = os.open(os.devnull, os.O_WRONLY)
    oldStderr= os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    audioPyAudio = pyaudio.PyAudio()
    os.dup2(oldStderr, 2)
    os.close(oldStderr)

    try:
        deviceInfo = audioPyAudio.get_default_input_device_info()
        audioChannels = int(deviceInfo.get('maxInputChannels',2))
        audioRate = int(deviceInfo.get('defaultSampleRate',24000))
        if audioChannels > 2:
            audioChannels = 2
        elif audioChannels < 1:
            audioChannels = 1
    except:
        audioChannels = 2
        audioRate = 24000
    try:
        audioStream = audioPyAudio.open(format=pyaudio.paInt16,
                                        channels=audioChannels,
                                        rate=audioRate,
                                        input=True,
                                        frames_per_buffer=1024
                                        )
    except Exception as ex:
        print(f"Kritik Mikrofon Hatasi: {ex}")
        return

    audioFrames = []
    isAudioRecord = True

# ---------- Ses Yakalama Fonksiyonları ----------
    def RecordAudio():
        while isAudioRecord:
            try:
                data = audioStream.read(1024, exception_on_overflow=False)
                if micActive:
                    audioFrames.append(data)
                else:
                    audioFrames.append(b'\x00' * len(data))
            except:
                audioFrames.append(b'\x00' * 2048)
                time.sleep(0.01)
                continue
    global audioThread
    audioThread = threading.Thread(target=RecordAudio, daemon=True)
    audioThread.start()

def _StopAudio(filename):
    global audioStream, audioPyAudio, audioFrames, isAudioRecord,audioChannels,audioRate
    isAudioRecord = False
    time.sleep(0.3)
    print(f"Yakalanan Ses Paketi Sayısı: {len(audioFrames)}")
    try:
        if len(audioFrames) == 0:
            fakeSound = b'\x00' * int(24000 * 2 * 2)
            audioFrames.append(fakeSound)
    except Exception as ex:
        print(f"Sahte ses hatasi: {ex}")

    try:
        print(f"Wav dosyasi yaziliyor: {filename}")
        with wave.open(filename, 'wb') as wf:
            channel = int(audioChannels) if 'audioChannels' in globals() else 2
            speed = int(audioRate) if 'audioRate' in globals() else 24000

            wf.setnchannels(channel)
            wf.setsampwidth(2)
            wf.setframerate(speed)
            wf.writeframes(b''.join(audioFrames))
    except Exception as ex:
        print(f"KRITIK HATA: Ses yazilamadi! {ex}")

    try:
        if audioStream:
            audioStream.stop_stream()
            audioStream.close()
        if audioPyAudio:
            audioPyAudio.terminate()
    except Exception as ex:
        print(f"Motor Kapatma Hatasi: {ex}")

def _MergeAudioVideo(videoPath,audioPath,finalPath,actualFPS):
    global activeTasks
    activeTasks += 1
    safeFPS = round(actualFPS,2) if actualFPS > 0.1 else 10.0
    try:
        if os.path.exists(audioPath) and os.path.exists(videoPath):
            cmd = ['ffmpeg', '-y',
                '-r', str(safeFPS),
                '-i', videoPath,
                '-i', audioPath,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-af', 'aresample=async=1',
                '-c:a', 'aac',
                '-ac', '2',
                finalPath]
            result = subprocess.run(cmd,capture_output=True, text= True)
            if result.returncode == 0:
                print(f"Başarıyla Kaydedildi {finalPath}")
                if os.path.exists(videoPath): os.remove(videoPath)
                if os.path.exists(audioPath): os.remove(audioPath)
            else:
                print(f"FFMPEG HATASI: {result.stderr}")
        else:
            print("HATA: Birlestirilecek video veya ses dosyasi bulunamadi!")
    except Exception as ex:
        print(f"Merge Hatasi: {ex}")
    finally:
        activeTasks -= 1
        print("--- BIRLESTIRME ISLEMI BITTI ---")


# ---------- Kamera ile Alakalı Fonksiyonlar ----------
def _CameraButton(btn,video,debugVideo,recBTN=None):
    global cameraActive, manualRecord
    if not cameraActive:
        _StartCamera(btn,video,debugVideo)
        btn.configure(text="Kamerayı Kapat",fg_color="#cd3333")
    else:
        cameraActive = False
        manualRecord = False
        btn.configure(text="Kamerayı Çalıştır",fg_color="#2ecc71")

        if recBTN and recBTN.winfo_exists():
            recBTN.configure(text="Kayda Başla", fg_color="#f1c04f", text_color="black")

        blankImg = ctk.CTkImage(light_image=Image.new("RGB", (1,1), "black"),size=(1,1))

        if video.winfo_exists():
            video.configure(image=blankImg,text="Sistemi Başlatın...")
        if debugVideo.winfo_exists():
            debugVideo.configure(image=blankImg, text="Sistemi Başlatın...")

def _StartCamera(btn,video,debugVideo):
    global cameraActive, capture
    if cameraActive: return
    capture = cv2.VideoCapture(0)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not capture.isOpened():
        messagebox.showwarning("Hata","Kamera Algılanmadı ve ya açılamadı")
        return
    cameraActive = True
    threading.Thread(target=lambda: _CameraLoop(video, debugVideo), daemon=True).start()

def _StartNewRecord(typeName):
    global videoTemp,audioTemp,finalMpFour,out,recordTime,frameCounter,savePath
    try:
        savePath = _ConfigManager("get", "SavePath")

        if not savePath:
            print("HATA: Kayıt yolu seçilmedi!")
            return
        if _CheckFreeSpace(savePath) >= 1:
            print(f"\n[{typeName}] Kayıt İşlemi Başlatılıyor...")
            recordTime = time.time()
            frameCounter = 0
            width, height = 640, 480
            savePath = _ConfigManager("get", "SavePath")
            baseName = f"{savePath}/Rec_{int(time.time())}"

            videoTemp = f"{baseName}.avi"
            audioTemp = f"{baseName}.wav"
            finalMpFour = f"{baseName}.mp4"

            _StartAudio(audioTemp)
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            out = cv2.VideoWriter(videoTemp, fourcc, 10, (width,height),True)
        else:
            messagebox.showwarning("Depolama Alanı Yetersiz!",
                                "Depolama alanınız yetersiz lütfen 1GB dan fazla bir depolama alanı seçiniz")
    except Exception as ex:
        messagebox.showerror("HATA!!",f"Kayıt devam ederken ya da başlatılırken bir hata oluştu \n{ex}")
        if 'out' in locals() and out is not None:
            out.release()
        out = None

def _StopCurrentRecord():
    global videoTemp,audioTemp,finalMpFour,out,recordTime,frameCounter
    print("\n[SİSTEM] Kayıt durduruldu, MP4 birleştirme başlıyor...")
    duration = time.time() - recordTime
    actualFPS = frameCounter / duration if duration > 0 else 10

    if out is not None:
        out.release()
        out = None

    time.sleep(0.5)
    _StopAudio(audioTemp)
    threading.Thread(target=_MergeAudioVideo, args=(videoTemp, audioTemp, finalMpFour, actualFPS), daemon=True).start()

def _CameraLoop(video, debugVideo):
    global cameraActive,capture,lastWarning,videoTemp,audioTemp,finalMpFour,out,frameCounter

    firstFrame = None
    timer = 0
    isRecording = False
    recordingType = None
    savePath = _ConfigManager("get", "SavePath")

    while cameraActive:
        autoRecCsv = _ConfigManager("get", "KayitActive") == "True"
        sensitivity = int(_ConfigManager("get","Sensitivity")or 25)
        alarmPerSecond = int(_ConfigManager("get","AlarmValue") or 0)
        try:
            success,frame = capture.read()
            if not success: break
            frameResized = cv2.resize(frame,(640,480))
            gray = cv2.cvtColor(frameResized,cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray,(21,21),0)

            if firstFrame is None:
                firstFrame = gray
                continue
            find = cv2.absdiff(firstFrame,gray)
            _,threshold = cv2.threshold(find,sensitivity,255,cv2.THRESH_BINARY)
            threshold = cv2.erode(threshold,None,iterations = 2)

            contours,_=cv2.findContours(threshold.copy(),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)

            movementDetected = False
            allX ,allY = [],[]

            for con in contours:
                if cv2.contourArea(con) < 500: continue
                movementDetected = True
                (x,y,w,h) = cv2.boundingRect(con)
                allX.extend([x, x + w])
                allY.extend([y, y + h])

            if movementDetected:
                minX, maxX = min(allX), max(allX)
                minY, maxY = min(allY), max(allY)
                cv2.rectangle(frameResized, (minX, minY), (maxX, maxY), (0, 0, 190), 2)
                timer = time.time()

            autoRecPossible = autoRecCsv and (time.time()-timer) < 3
            if manualRecord:
                if not isRecording:
                    _StartNewRecord("Manual")
                    isRecording = True
                    recordingType = "Manual"
            elif autoRecPossible:
                if not isRecording:
                    _StartNewRecord("Auto")
                    isRecording = True
                    recordingType = "Auto"
            elif isRecording:
                if (recordingType == "Manual" and not manualRecord)or \
                    (recordingType == "Auto") and not autoRecPossible:
                    _StopCurrentRecord()
                    isRecording = False
                    recordingType = None
            if isRecording and out is not None:
                out.write(frameResized.copy())
                frameCounter += 1
                cv2.circle(frameResized, (610, 30), 8, (0, 0, 255), -1)

            if movementDetected and alarmPerSecond > 0:
                if (time.time() - lastWarning) >= alarmPerSecond:
                    _PlayBeep()
                    lastWarning = time.time()
            try:
                imgRgb = cv2.cvtColor(frameResized, cv2.COLOR_BGR2RGB)
                ctkImg = ctk.CTkImage(Image.fromarray(imgRgb), size=(625, 600))
                ctkDebug = ctk.CTkImage(Image.fromarray(threshold), size=(625, 600))

                if video.winfo_exists():
                    video.configure(image=ctkImg, text="")
                    video.imgtk = ctkImg
                if debugVideo.winfo_exists():
                    debugVideo.configure(image=ctkDebug, text="")
                    debugVideo.imgtk = ctkDebug
            except: break
            firstFrame = gray
            time.sleep(0.1)
        except:break
    if 'out' in locals() and out is not None:
        out.release()
    if capture: capture.release()

def _ManualRecord():
    global manualRecord, manualRecBTN
    if not cameraActive:
        messagebox.showwarning("Uyarı", "Kayıt alabilmek için önce 'Çalıştır' butonuna basmalısınız!")
        return
    manualRecord = not manualRecord
    if manualRecBTN and manualRecBTN.winfo_exists():
        if manualRecord:
            manualRecBTN.configure(
                text="Kaydı Durdur",
                fg_color="#cd3333",
                text_color="white"
            )
        else:
            manualRecBTN.configure(
                text="Kayda Başla",
                fg_color="#1a1a1a",
                text_color="#f1c04f"
            )


# ---------- Alarm Sesi (Linux İçin) ----------
def _PlayBeep():
    os.system('play -nq -t alsa synth 0.1 sine 2000> /dev/null 2>&1 &')

# ---------- Csv Dosya İsmi (Kayıt/Ayarlar Dosyasının Yolunu Görmek İçin Gerkli) ----------
if getattr(sys, 'frozen', False):
    basePath = os.path.dirname(sys.executable)
else:
    basePath = os.path.dirname(os.path.abspath(__file__))

configDir = os.path.join(basePath, "config")
configCsv = os.path.join(configDir, "HASSettings.csv")

def _ConfigManager(action = "get", key="SavePath", value=None):
    if not os.path.exists(configDir):
        os.makedirs(configDir, exist_ok=True)

    if not os.path.isfile(configCsv):
        with open(configCsv, "w", newline='', encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Settings", "Value"])
            writer.writerows([
                ["SavePath", "None"],
                ["Sensitivity", "100"],
                ["AlarmValue", "1"],
                ["KayitActive","False"],
                ["MikrafonActive", "False"]
            ])

    if action == "get":
        try:
            with open(configCsv, "r", encoding="utf-8") as file:
                rows = [r for r in csv.reader(file) if len(r)>=2]
                for row in rows:
                    if row[0].strip() == key:
                        value = row[1].strip()
                        if key == "SavePath":
                            return value if value != "None" and os.path.exists(value) else None
                        return value
            return None
        except: return None

    elif action == "set":
        try:
            with open(configCsv, "r", encoding="utf-8") as file:
                rows = [r for r in csv.reader(file) if len(r) >= 2]
            founded = False
            for row in rows:
                if row[0].strip() == key:
                    row[1] = str(value)
                    founded = True

            if not founded: rows.append([key, str(value)])
            with open(configCsv, "w",newline='' ,encoding="utf-8") as file:
                csv.writer(file).writerows(rows)
            return True
        except Exception as ex:
            messagebox.showwarning("HATA", f"Hay Aksi! Bir hata oluştu\n {ex}")
            return False

def _SelectFolder():
    selectPath = filedialog.askdirectory(title="Kayıtların Kaydedileceği Klasörü Seçiniz.")
    if selectPath:
        tester= os.path.join(selectPath, "test.tmp")
        try:
            with open(tester, "w") as file:
                file.write("test")
            os.remove(tester)

            correctPath = os.path.join(selectPath, "HAS Records").replace("\\","/")
            if not os.path.isdir(correctPath):
                os.mkdir(correctPath)
            _ConfigManager("set", "SavePath", correctPath)
            return  correctPath
        except (PermissionError, OSError):
            messagebox.showwarning(
                "Yetki Hatası",
                "Seçtiğiniz alan yazma korumalıdır.\n\n"
                "Programı yönetici olarak çalıştırın veya yazma korumalı olmayan bir yol seçiniz."
            )
            return None
    return None

def _IsFolderSelected():
    recordPath = _ConfigManager("get", "SavePath")
    if not recordPath:
        response = messagebox.askyesno(
            "Kayıt Alanı Seçilmemiş.",
            "Kayıt alındığında kayıt yapmam için bir yer seçmeniz gereklidir.\nŞimdi seçmek ister misiniz?"
        )
        if response:
            return bool(_SelectFolder())
        return False
    return True

def _ChangeFolderDir(changeDir):
    newPath = _SelectFolder()
    if newPath:
        changeDir.configure(text=newPath)
        _OpenAyarlarScreen()

def _CheckFreeSpace(path):
    checkPath = path if path else "/"

    total, used, free = shutil.disk_usage(checkPath)
    freeStorage = free / (1024**3)
    return freeStorage

def _ToggleSettings(settingKey):
    currentValue = _ConfigManager("get", settingKey)
    newValue = "False" if currentValue == "True" else "True"
    _ConfigManager("set", settingKey, newValue)
    _OpenAyarlarScreen()

# ---------- Sayfa Temizleme Fonksiyonu ----------
def _ClearMainContent():
    global cameraActive,capture
    cameraActive = False
    if capture is not None and capture.isOpened():
        capture.release()
        try:
            capture.release()
        except Exception as ex:
            print(ex)
    for widget in window.winfo_children():
        if widget != topBar:
            widget.destroy()

# ---------- Topbar daki Buton Aktivite Takip Fonksiynu ----------
def _UpdateNavButtons(activeBTN):
    buttons = [ekranBTN, hakkindaBTN, ayarlarBTN]

    for btn in buttons:
        if btn == activeBTN:
            btn.configure(
                fg_color = activeBTNColor,
                hover_color = pressedBTNColor
            )
        else:
            btn.configure(
                fg_color ="transparent",
                hover_color = activeBTNColor
            )


# ---------- Renkler ----------
topbarBgColor = "#44444E"
activeBTNColor = "#a6a6a7"
pressedBTNColor = "#79797c"
bgColor = "#37353E"
activetedBTNColor = "#006b3c"
disabledBTNColor = "#cd3333"
windowBgColor = "#44444E"

# ---------- Pencere/Stil Ayarları ----------
window = ctk.CTk()
window.configure(background= bgColor)
window.title("HAS Project - Hareket Algılama Sistemi")
window.geometry("1440x900")
ctk.set_widget_scaling(1.6)
ctk.set_window_scaling(1.6)
window.protocol("WM_DELETE_WINDOW", _OnAppClose)

def _ToggleMic(btn):
    global micActive
    current = _ConfigManager("get", "MikrafonActive") == "True"
    newState = "False" if current else "True"
    _ConfigManager("set", "MikrafonActive", newState)

    micActive = (newState == "True")

    if newState == "True":
        btn.configure(text="Mikrafon: Açık")
    else:
        btn.configure(text="Mikrafon: Kapalı")


def _OpenEkranScreen():
    global micActive,manualRecBTN
    _UpdateNavButtons(ekranBTN)
    _ClearMainContent()
    if not _IsFolderSelected(): return
    isKayitActive = _ConfigManager("get", "KayitActive") == "True"
    isMikrafonActive = _ConfigManager("get", "MikrafonActive") == "True"
    micActive = isMikrafonActive
    AlarmValue = int(_ConfigManager("get", "AlarmValue") or 0)
    text = "Kapalı" if AlarmValue == 0 else str(AlarmValue)
    micText = "Mikrafon: Açık" if isMikrafonActive else "Mikrafon: Kapalı"
    kayitT = "Oto Kayıt: Aktif" if isKayitActive else "Oto Kayıt: Kapalı"

    cameraFrame = ctk.CTkFrame(
        window,
        width=1250,
        height=600,
        fg_color="black",
        corner_radius=15
    )
    cameraFrame.pack(pady=10)
    cameraFrame.grid_propagate(False)
    cameraFrame.grid_columnconfigure(0, weight=1)
    cameraFrame.grid_columnconfigure(1, weight=1)
    cameraFrame.rowconfigure(0, weight=1)
    videoLBL = ctk.CTkLabel(
        cameraFrame,
        text="Sistemi Başlatın...",
        font=("Segoe UI", 18),
        text_color="gray",
    )
    videoLBL.grid(row=0, column=0, sticky="nsew")
    debugLBL = ctk.CTkLabel(
        cameraFrame,
        text="Sistemi Başlatın....",
        font=("Segoe UI", 18),
        text_color="gray"
    )
    debugLBL.grid(row=0, column=1, sticky="nsew")
    controlFrame = ctk.CTkFrame(
        window,
        fg_color="transparent"
    )
    controlFrame.pack(pady=10, fill="x")
    controlFrame.grid_columnconfigure((0, 1, 2, 3), weight=1)
    startBTN = ctk.CTkButton(
        controlFrame,
        text="Çalıştır",
        fg_color="#2ecc71",
        hover_color="#27ae60",
        width=180,
        height=45,
        font=("Segoe UI", 16, "bold"),
        command=lambda: _CameraButton(startBTN, videoLBL, debugLBL, manualRecord),
        cursor="hand2"
    )
    startBTN.grid(row=0, column=0, pady=(0,10))
    if not isKayitActive:
        if manualRecord:
            btnText = "Kaydı Durdur"
            btnColor = "#cd3333"
            btnTextColor = "white"
        else:
            btnText = "Kayda Başla"
            btnColor = "#1a1a1a"
            btnTextColor = "#f1c04f"

        manualRecBTN = ctk.CTkButton(
            controlFrame,
            text=btnText,
            fg_color=btnColor,
            text_color=btnTextColor,
            border_width=1,
            border_color="#f1c04f",
            width=180,
            height=45,
            command=_ManualRecord,
            cursor="hand2"
        )
        manualRecBTN.grid(row=1, column=0)
    currentCol = 1
    alarmIndicator = ctk.CTkButton(
        controlFrame,
        text=f"Alarm Süresi: {text}",
        state="disabled",
        fg_color="#1a1a1a",
        text_color="#e74c3c",
        border_width=1,
        border_color="#e74c3c",
    )
    alarmIndicator.grid(row=0, column=currentCol, padx=10)
    currentCol += 1
    kayitBTN = ctk.CTkButton(
        controlFrame,
        text=kayitT,
        state="disabled",
        fg_color="#1a1a1a",
        text_color="#2ecc71",
        border_width=1,
        border_color="#2ecc71",
    )
    kayitBTN.grid(row=0, column=currentCol, padx=10)
    currentCol += 1
    mikrafonIndicatorBTN = ctk.CTkButton(
        controlFrame,
        text=micText,
        fg_color="#1a1a1a",
        text_color="#3498db",
        border_width=1,
        cursor="hand2",
        border_color="#3498db",
        command=lambda: _ToggleMic(mikrafonIndicatorBTN)
    )
    mikrafonIndicatorBTN.grid(row=0, column=currentCol, padx=10)
    currentCol += 1

def _OpenHakkindaScreen():
    _UpdateNavButtons(hakkindaBTN)
    _ClearMainContent()

    pythonVersion = platform.python_version()
    projectVersion = "1.5.3"
    ctkVersion = ctk.__version__
    openCVVersion= cv2.__version__
    projectName = "HAS Project Group"
    MITLicense = "Bu proje MIT Lisansı standartlarında korunmaktadır."
    copyright = "© 2026 HAS Project Group. Tüm Hakları Saklıdır."

    brandTitleLBL = ctk.CTkLabel(
        window,
        text= projectName,
        font=("Segoe UI",25,"bold"),
        text_color = activeBTNColor
    )
    brandTitleLBL.pack(pady = (40,5))
    versionFrame = ctk.CTkFrame(
        window,
        fg_color="#44444E",

    )
    versionFrame.pack(pady=10)
    versionLBL = ctk.CTkLabel(
        versionFrame,
        text= projectVersion,
        font=("Segoe UI", 12,"bold")
    )
    versionLBL.pack(padx= 10, pady = 5)
    devDetails = ("---------- GELİŞTİRİCİLER ----------\n\n"
                  "*   Enes Batur TOPAL\n*   Yasin TAN\n*   Yaşar PARLAK")
    devsLBL = ctk.CTkLabel(
        window,
        text= devDetails,
        font=("Consolas", 14),
        justify="left",
    )
    devsLBL.pack(pady=25)
    systemDetails= (f"* Yazılım Mimarisi:   CustomTkinter v{ctkVersion}\n"
                    f"* Görüntü İşleme:     OpenCV v{openCVVersion}\n"
                    f"* Çalışma Ortamı:     Python v{pythonVersion} - {_GetArchitecture()}\n"
                    f"* Sistem Altyapısı:   {_GetRealOs()}")
    systemDetailsLBL = ctk.CTkLabel(
        window,
        text=systemDetails,
        font=("Consolas", 12),
        text_color="#A6A6A7",
        justify="left"
    )
    systemDetailsLBL.pack(pady=20)
    footerLBL = ctk.CTkLabel(
        window,
        text=f"{MITLicense}\n{copyright}",
        font=("Segoe UI",11),
        text_color="gray"
    )
    footerLBL.pack(side="bottom", pady=20)

def _GetArchitecture():
    machine = platform.machine().lower()
    if "64" in machine:
        return "x64"
    elif "86" in machine or "32" in machine:
        return "x86"
    else:
        return machine

def _GetRealOs():
    osName = platform.system()
    osRelease = platform.release()
    osVersion = platform.version()

    if osName == "Windows":
        try:
            buildNumber = int(osVersion.split(".")[-1])
            if buildNumber >= 22000:
                return f"Windows 11 (Build {buildNumber})"
            else:
                return f"Windows (Build {osRelease})"
        except:
            return f"Windows (Build {osRelease})"
    elif osName == "Linux":
        try:
            info = {}
            with open("/etc/os-release") as about:
                for line in about:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        info[key] = value.strip('"')
            distro = info.get("PRETTY_NAME") or info.get("NAME") or "Linux"
            return distro
        except:
            return f"Linux {osRelease}"
    return f"{osName} ({osRelease})"

def _OpenAyarlarScreen():
    _UpdateNavButtons(ayarlarBTN)
    _ClearMainContent()
    global alarmBTN,kayitBTN,mikrafonBTN
    ayarlarMainGrid = ctk.CTkFrame(window,fg_color=windowBgColor)
    ayarlarMainGrid.pack(padx = 40, pady = (0,20),fill = "x")
    ayarlarMainGrid.grid_columnconfigure(0, weight=1)
    segmentedFrame = ctk.CTkFrame(ayarlarMainGrid,fg_color="transparent")
    segmentedFrame.grid(row=0, column=1, padx=180,pady=(20,0), sticky="e")
    pathData = _ConfigManager("get","SavePath")
    currentPath = pathData if pathData else "Seçilmedi / Geçersiz"
    btnFolderConfigC=disabledBTNColor if not pathData else activeBTNColor
    btnFolderConfigT="Seç..." if not pathData else "Değiştir..."
    KayitActive = _ConfigManager("get","KayitActive") == "True"
    currentValue = int(_ConfigManager("get","AlarmValue")or 0)

    def _UpdateAlarm(value):
        currentValue = int(_ConfigManager("get", "AlarmValue") or 0)
        newValue = currentValue + value
        if 0 <= newValue <= 10:
            AlarmValue = newValue
            _ConfigManager("set", "AlarmValue", AlarmValue)
            valueLBL.configure(text=newValue)
            if AlarmValue == 0:
                minusBTN.configure(state="disabled", fg_color="#555555")
                text = "Kapalı"
                valueLBL.configure(text=text)
            else:
                minusBTN.configure(state="normal", fg_color=activeBTNColor)
                text = newValue
                valueLBL.configure(text=text)
            if AlarmValue == 10:
                plusBTN.configure(state="disabled", fg_color="#555555")
            else:
                plusBTN.configure(state="normal", fg_color=activeBTNColor)

    alarmLBL = ctk.CTkLabel(
        ayarlarMainGrid,
        text="Alarm Saniye Ayarı:",
        font= ("Segoe UI", 15,"bold"),
    )
    valueLBL = ctk.CTkLabel(
        segmentedFrame,
        text= currentValue,
        font= ("Segoe UI", 15,"bold"),
        text_color="gray",
    )
    kayitLBL = ctk.CTkLabel(
        ayarlarMainGrid,
        text="Otomatik Kayıt:",
        font=("Segoe UI",15,"bold")
    )
    folderLBL = ctk.CTkLabel(
        ayarlarMainGrid,
        text="Klasör:",
        font=("Segoe UI",15,"bold")
    )
    folderInfoLBL = ctk.CTkLabel(
        ayarlarMainGrid,
        text=currentPath,
        font=("Consolas", 11),
        text_color=activeBTNColor,
        wraplength=300
    )
    plusBTN = ctk.CTkButton(
        segmentedFrame,
        text="+",
        width=70,
        height=35,
        border_color="#777777",
        fg_color=activeBTNColor,
        cursor="hand2",
        command=lambda: _UpdateAlarm(1)
    )
    minusBTN = ctk.CTkButton(
        segmentedFrame,
        text="-",
        width=70,
        height=35,
        border_color="#777777",
        fg_color=activeBTNColor,
        cursor="hand2",
        command=lambda: _UpdateAlarm(-1)
    )
    kayitBTN = ctk.CTkButton(
        ayarlarMainGrid,
        text="Otomatik" if KayitActive else "Manual",
        font= ("Segoe UI", 16,"bold"),
        fg_color=activeBTNColor if KayitActive else disabledBTNColor,
        hover_color= activeBTNColor,
        corner_radius= 10,
        border_width= 0,
        cursor="hand2",
        command=lambda:_ToggleSettings("KayitActive")
    )
    folderBTN = ctk.CTkButton(
        ayarlarMainGrid,
        text=btnFolderConfigT,
        font= ("Segoe UI", 16,"bold"),
        fg_color=btnFolderConfigC,
        hover_color= pressedBTNColor,
        corner_radius= 10,
        border_width= 0,
        cursor="hand2",
        command=lambda: _ChangeFolderDir(folderInfoLBL)
    )
    alarmLBL.grid(row= 0 , column= 0,padx=180,pady=20,sticky="w")
    kayitLBL.grid(row= 1 , column= 0,padx=180,pady=20,sticky="w")
    folderLBL.grid(row= 2 , column= 0,padx=180,pady=(20,0),sticky="w")
    folderInfoLBL.grid(row=3, column=0, padx=180, pady=(0,20), sticky="w")
    valueLBL.grid(row=1, column= 0,columnspan=2,pady=(5,0),sticky="n")
    plusBTN.grid(row= 0, column= 0)
    minusBTN.grid(row= 0, column= 1)
    kayitBTN.grid(row= 1,column = 1, padx=180,pady=20,sticky="e")
    folderBTN.grid(row= 2,column = 1,rowspan=2 ,padx=180,pady=20,sticky="e")
    _UpdateAlarm(0)

# ---------- Topbar Ayarları ----------
topBar = ctk.CTkFrame(
    window,
    fg_color= topbarBgColor,
    height=70
    )
topBar.pack(side="top", fill="x", padx=40, pady=20)
topBar.grid_columnconfigure(0,weight=0)
topBar.grid_columnconfigure(1,weight=0)
topBar.grid_columnconfigure(2,weight=1)
topBar.grid_columnconfigure(3,weight=0)
ekranBTN = ctk.CTkButton(
    topBar,
    text="Ekran",
    width=120,
    height=40,
    corner_radius=10,
    fg_color= "transparent",
    font=("Segoe UI", 14,"bold"),
    command=_OpenEkranScreen,
    cursor="hand2"
)
hakkindaBTN = ctk.CTkButton(
    topBar,
    text="Hakkında",
    width=120,
    height=40,
    corner_radius=10,
    fg_color= "transparent",
    font=("Segoe UI", 14,"bold"),
    command=_OpenHakkindaScreen,
    cursor="hand2"
)
ayarlarBTN = ctk.CTkButton(
    topBar,
    text="Ayarlar",
    width=120,
    height=40,
    corner_radius=10,
    fg_color= "transparent",
    font=("Segoe UI", 14,"bold"),
    command=_OpenAyarlarScreen,
    cursor="hand2"
)
ekranBTN.grid(row = 0 , column = 0, padx = 10 ,pady = 10)
hakkindaBTN.grid(row = 0 , column = 1, padx = 10 ,pady = 10)
ayarlarBTN.grid(row = 0 , column = 3, padx = 10 ,pady = 10)

_OpenHakkindaScreen()
window.mainloop()