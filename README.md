# UN Aurora Lite 0.1.2

為 **Sulkan 0.4.2 / Minecraft Java 26.2 / Sodium 0.9.1** 製作的輕量原生光影包，預設以日常遊玩的清晰度與自然觀感為目標。
已通過發布版載入器檢查，以及軟體 Vulkan 的後製像素測試；**尚未在 Minecraft 世界中實測畫面或 FPS**。

## 安裝

1. 使用 Minecraft 26.2、Java 25、Fabric Loader 0.18.4 以上、對應 26.2 的 Fabric API 0.155.0 以上、Sodium 0.9.1 以上和 **Sulkan 0.4.2**。
2. 確認遊戲正在使用 Vulkan。開啟遊戲的 **Video Settings → Shaders → Open Shader Pack Folder**。
3. 把 `UN_Aurora_Lite-0.1.2-Sulkan-0.4.2.zip` **原封不動**放入該資料夾。一般路徑是遊戲實例的 `.minecraft/shaders/`。
4. 在 Shaders 畫面選取這個 ZIP、開啟光影。點 **Pack Settings** 調整效果。

已使用 0.1.0／0.1.1 的話，將新版 ZIP 放入同一個資料夾，再選取名稱含 0.1.2 的包；舊版的包內設定不會自動套到新版。

這是 Sulkan native graph ZIP；安裝位置是 `shaders/`。Iris 的 `shaderpacks/` 不會載入它。
啟動器若開了版本隔離，以遊戲內開啟的資料夾為準。

## 效果

- 暖色陽光與火把、冷色環境光、少量背光樹葉透光。日夜交界平滑淡入淡出，夜晚預設稍亮，洞穴有可調的局部補光。
- 亮處使用柔和高光壓縮，暗部對比保留接近黑色的差異；曝光與對比不會把純黑整體抬灰。
- 使用 Sulkan 的動態地形與附近實體投影，預設 Low、64 格。
- 植物擺動與陰影投影共用載入器的風場，降低兩者錯位的風險。
- 水面保留生態域水色、深度吸收與微弱波紋；降低反射遮擋水底的程度，雨天反射跟隨陰天色調。遠處的細水波會淡出，以降低閃爍。
- 雨天增加少量濕潤反光，只作用於露天、朝上的表面，預設強度 0.35；可單獨關閉。
- 半解析度接觸陰影，深度加權放大以減少輪廓黑邊；暗部會減弱遮蔽，避免坑洞與台階變成黑塊。
- 四分之一解析度柔和光暈、曝光與色調調整、可選輕量邊緣平滑；手持物排除光暈和平滑，也不會向旁邊的世界畫面產生光暈。
- 天空與霧使用固定、低於一個 8-bit 色階的抖色，減少色帶；可關閉，純黑保持純黑。
- 天空、日月、星星和雲由原版渲染。地獄與終界沿用原版環境與地形光照貼圖。

關閉 `AO_QUALITY` 或把 `AO_STRENGTH` 設成 0，載入器會移除 AO 步驟與其貼圖。
把 `BLOOM_STRENGTH` 設成 0，會移除三個光暈步驟與貼圖。
水面反射使用天空近似色，沒有螢幕空間世界反射、光線追蹤或體積雲運算。

## 先用這組設定

| 選項 | 預設／舊顯卡起點 | 較高畫質 |
| --- | --- | --- |
| Shadow quality | 1：Low | 2：Medium |
| Shadow distance | 64 | 96 |
| Contact shadows | 1：4 samples | 2：8 samples |
| Contact shadow strength | 0.45 | 0.6 |
| Soft bloom | 0.06 | 0.08 |
| Foliage movement | 0.5 | 1 |
| Water ripple strength | 0.5 | 1 |
| Water absorption | 0.75 | 1 |
| Analytic sky reflection | 0.35 | 0.5 |
| Night ambient brightness | 1.25 | 1.25 |
| Unlit interior visibility | 0.65 | 0.65 |
| Rain surface sheen | 0.35 | 0.65 |
| Smooth sky and fog gradients | 1 | 1 |
| Light edge smoothing | 0 | 1 |

1 GB 顯卡建議先以 1280×720 或 1920×1080、6～8 區塊測試。
若幀時間不穩，先關接觸陰影和邊緣平滑，再降低陰影。尚無實機效能數字。
0.1.2 沒有新增渲染步驟或中間貼圖；仍有額外運算和光暈手部取樣的成本。
96 格外的接觸陰影會略過周圍深度取樣，雨天濕潤效果可用 `WET_SURFACES=0` 完全移除。

依載入器公式估算，1080p 預設設定的 graph 中間貼圖約 **27.69 MiB**；
包含保守的場景擷取與陰影預算約 **81.30 MiB**。這不是整個遊戲的顯存用量，
不含原版渲染目標、材質、區塊網格、驅動配置和切換時可能並存的舊資源。
manifest 的 `budgetMiB: 448` 是檢查上限，不是啟動時固定配置 448 MiB。

## 已驗證的範圍

檢查基準是 2026-09-08 發布的 `sulkan-0.4.2-26.2.jar`，
配合 Minecraft 26.2 的原版類別與 LWJGL 3.4.1。沒有改寫解析器或建立假 frame 定義。

- 發布版 `ShaderPackScanner` 接受 ZIP。
- 發布版 `PackFiles.read`、`PackGraph.parse` 接受格式、檔案路徑和渲染流程。
- 全部 22 個選項、83 個允許值通過原版選項驗證。
- 21 組設定包含陰影 0～3、水面開關、AO 開關／品質、光暈開關、邊緣平滑、濕潤效果及抖色開關。
- 199 個模組由原版 `NativeShaderCompiler` 編譯成 Vulkan 1.2 SPIR-V，並經 Minecraft 的 SPIRV-Cross 反射與 `rebind` 檢查。
- `spirv-val`、跨階段介面、Sodium 頂點格式、UBO 與 push constant 位移檢查。
- 720p、1080p、1440p、4K 的 graph 資源預算檢查；所有選項最高值也在 manifest 預算內。
- Mesa 25.2.8 lavapipe 軟體 Vulkan 建立裝置與後製 pipeline，完成 9 次合成紋理繪製：驗證手部光暈排除、世界光暈保留、抖色穩定、黑色保留，以及平面／遠景／天空的 AO。

這些合成紋理測試不包含 Minecraft 世界；Fabric/Sodium mixin 套用、地形 pipeline、世界繪製、畫質、FPS、硬體驅動相容性和其他模組共存仍待實機確認。
編譯成功不等於已通過完整遊戲載入與繪製。詳細結果見 `VALIDATION.md` 與 `validation/summary.json`。

## 五分鐘實機檢查

1. 先記下 Sulkan 內建包能否正常運作，再切到本包。確認沒有自動退回內建包。
2. 白天看樹影、草地與水岸；手持方塊轉動視角，檢查黑塊、閃爍及手部黑邊。
3. 看火把房間、夜晚、下雨、潛水；再切換地獄與終界。
4. 把 Shadow quality 依序設 0、1，Water refraction 設 0、1；確認關閉光暈和接觸陰影後畫面仍正常。
5. 退出重進一次，確認選擇仍保留。若報錯，提供該實例 `logs/latest.log` 中 Sulkan、shader、pipeline 相關段落及截圖。

## 編輯與重新打包

直接修改 `shaders/` 的 GLSL。選項預設值位於 `sulkan.json` 的 `options`；
新的 `default` 必須同時出現在該選項的 `values` 裡。native 格式版本是整數 `1`。

```bash
python3 tools/build.py --output UN_Aurora_Lite-0.1.2-Sulkan-0.4.2.zip
```

ZIP 根目錄必須直接包含 `sulkan.json` 和 `shaders/`。
自動化驗證程式在 `tools/`；重現方式見 `VALIDATION.md`。

## 來源與授權

原生格式與示例取自 [Sulkan 0.4.2 發布版](https://modrinth.com/mod/sulkan/version/nCLRA6yu)。
官網 `base-shader.zip` 和公開 main 原始碼仍有舊格式，這個包以實際 0.4.2 JAR 為準。
本包的光照、水面、後製程式為本次撰寫；植物風場使用 Sulkan 的 GPLv3 helper。
授權及逐檔來源見 `THIRD_PARTY.md` 與 `LICENSE`。
