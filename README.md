# Auto Recap — Windows Local Setup (အခမဲ့)

ဒီ project က `index.html` နဲ့ `main.py` ကိုသုံးပြီး local website ကို ကိုယ့် Windows ကွန်ပျူတာပေါ်မှာ ဖွင့်ပေးပါတယ်။ Paid hosting မလိုပါ။ ဒီ version မှာ Windows Command Prompt က မြန်မာစာ encoding ကြောင့် command ကို မှားဖတ်နိုင်တဲ့ပြဿနာကို ရှောင်ရန် `.bat` script တွေကို ASCII စာသားသုံးပြီး ပြန်ရေးထားပါတယ်။

## လိုအပ်ချက်များ

- Windows 10/11 64-bit
- Python 3.11 64-bit
- Package/model download အတွက် internet
- AI packages နဲ့ video တွေအတွက် disk space လုံလောက်မှု
- Gemini API key (recap text ထုတ်ဖို့; Free Tier အသုံးပြုခွင့်/quota ရရှိမှုကို Google AI Studio မှာ စစ်ပါ)

## Install လုပ်ရန်

1. ZIP ကို Extract လုပ်ပါ။ ဥပမာ `C:\AutoRecap` လို folder ကို သုံးနိုင်ပါတယ်။ OneDrive folder သို့မဟုတ် Windows က ကာကွယ်ထားတဲ့ folder မသုံးတာ ပိုကောင်းပါတယ်။
2. Python 3.11 64-bit ကို https://www.python.org/downloads/release/python-3119/ မှ install လုပ်ပါ။ Install လုပ်စဉ် `Add Python to PATH` ကို အမှန်ခြစ်ပါ။
3. `install_windows.bat` ကို double-click လုပ်ပြီး အဆုံးထိ စောင့်ပါ။ CPU PyTorch နဲ့ website dependencies တွေ download/install လုပ်တာကြောင့် ကြာနိုင်ပါတယ်။
4. Window မှာ `INSTALLATION COMPLETED` လို့ပြမှ `start_windows.bat` ကို double-click လုပ်ပါ။
5. Command Prompt window ကို မပိတ်ပါနဲ့။ Browser မှာ http://127.0.0.1:8000 ကို ဖွင့်ပါ။

`127.0.0.1 refused to connect` ပေါ်ရင် server ကို start မလုပ်ရသေးတာ သို့မဟုတ် `start_windows.bat` ထဲက Python process ရပ်သွားတာ ဖြစ်နိုင်ပါတယ်။ အနက်ရောင် Command Prompt ထဲက error စာသားကို စစ်ပါ။ `INSTALLATION FAILED` ဆိုရင် installer အဆုံးက error message ကိုကြည့်ပါ။

## Gemini API key

Google AI Studio: https://aistudio.google.com/app/apikey

Key ကို website ထဲမှာပဲ ထည့်ပါ။ Source code နဲ့ screenshot တွေထဲမှာ မဖော်ပြပါနဲ့။ Free Tier quota ပြည့်ရင် request မအောင်မြင်နိုင်ပါတယ်။ Google Free Tier မှာ ပေးပို့တဲ့ transcript text ကို ထုတ်ကုန်တိုးတက်ရေးအတွက် အသုံးပြုနိုင်တယ်လို့ သတ်မှတ်ထားနိုင်တာကြောင့် အရေးကြီး/လျှို့ဝှက်တဲ့ စာသားတွေကို မပို့ခင် privacy terms ကို စစ်ပါ။

## Privacy နဲ့ output

ဗီဒီယိုမှ အသံထုတ်ခြင်း၊ local Whisper transcript နဲ့ local TTS/MP4 process တို့ကို ကွန်ပျူတာပေါ်မှာလုပ်ရန် ဒီ app ကို ရည်ရွယ်ထားပါတယ်။ Gemini recap အတွက် consent checkbox ကို အမှန်ခြစ်ပြီး submit လုပ်ရင် transcript စာသားကိုသာ Gemini API ဆီပို့ပါတယ်။ `uploads` နဲ့ `output` folder တွေမှာ source/ထွက်လာတဲ့ဖိုင်တွေ နေရာယူနိုင်ပါတယ်။

## အရေးကြီး

- ဒီ server က `127.0.0.1` မှာပဲ run တာဖြစ်ပြီး local use အတွက်ပါ။ Public internet ပေါ်ကို တိုက်ရိုက်မတင်ပါနဲ့။
- ပထမဆုံး Whisper နဲ့ MyanmarTTS model download ကြာနိုင်ပါတယ်။ CPU ပေါ်မှာ ဗီဒီယိုရှည်တွေကို process လုပ်တာလည်း ကြာနိုင်ပါတယ်။
- အမှားဖြစ်ရင် Command Prompt ကို မပိတ်ခင် screenshot ရိုက်ပါ။
