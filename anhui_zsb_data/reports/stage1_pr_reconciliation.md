# Stage 1 PR #2 / PR #3 证据收敛报告

> 生成时间：2026-08-15T02:49:24+00:00
> 比较对象：PR #2 与 PR #3 的实际资产清单、文件字节和路径

## 结论

- PR #3 继续作为唯一 Stage 1 主 PR。
- 未发现同一官方原始 URL 返回不可解释不同原件或无法解释的 SHA-256 漂移。
- 18 组 URL 相同但哈希不同均为原始 HTML/PDF 与派生文本的表示差异。
- 从 PR #2 迁移 33 个有效文件；两个 AHUA 2025 官方空白申请/承诺表经隐私复核后作为原始附件保留。
- PR #2 已过滤的 28 个跨页面公共图片继续排除。
- 收敛后：22 个 source document、60 个资产、60 个唯一 SHA-256。

## 汇总

| 指标 | 数量 |
|---|---:|
| 两个 PR 内容相同 | 24 |
| 仅 PR #2 文件 | 33 |
| 从 PR #2 迁移 | 33 |
| PR #2 独有但不迁移 | 0 |
| 仅 PR #3 文件 | 3 |
| URL 相同但哈希不同关系 | 18 |
| 未解释 URL/哈希冲突 | 0 |
| 哈希相同但路径不同 | 24 |
| 网站公共资源 | 28 |
| 最终 source document | 22 |
| 最终资产 | 60 |

## 仅 PR #2 存在

| 学校 | 年份 | Source | 类型 | 大小 | SHA-256 | PR #2 路径 | 处理 | PR #3 路径 |
|---|---:|---|---|---:|---|---|---|---|
| HFNU | 2024 | `SRC-HFNU-2024-ZC` | parsed_text | 34200 | `d7a6c2d2891bfe150ee5b26eb95a434cac3e6ba2f1673a6b15537a272a4d350c` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC_parsed.txt` |
| HFNU | 2024 | `SRC-HFNU-2024-LQ` | parsed_text | 4369 | `92da5bc14c5d7f4bad7fef4b24a72f091a12bc234f77663773e8565be75ed65c` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-LQ_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-LQ_parsed.txt` |
| HFNU | 2025 | `SRC-HFNU-2025-LQ` | parsed_text | 4443 | `6ce5faa25d110c659794d11848392cb2c52ad6e39da9081763fea05129c4512a` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-LQ_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-LQ_parsed.txt` |
| HFNU | 2026 | `SRC-HFNU-2026-LQ` | parsed_text | 1852 | `7fc2629c23dccf3ef767e2db8ae3f1d79f4e4dc16f66e8b22d890882eab592bf` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-LQ_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-LQ_parsed.txt` |
| HFNU | 2026 | `SRC-HFNU-2026-LQ` | document | 98816 | `8cad381fc97ae7da6c6c77fdb014158333d04a4f32f027f5ba8d0991e7ff0cc5` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-LQ-ATT-01.pdf` | migrate | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-LQ-EMBEDDED.pdf` |
| HFNU | 2024 | `SRC-HFNU-2024-DG` | parsed_text | 8579 | `f94ec9a6e060cf6b3bb40013e13394d71ac49c3683a9c4d0b40d9b37849b8d7a` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-DG_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-DG_parsed.txt` |
| HFNU | 2025 | `SRC-HFNU-2025-DG` | parsed_text | 9395 | `4af53aab6497776f3da040bbacbefd25bcf0e0dc09f63aed30d58608127f9f8a` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-DG_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-DG_parsed.txt` |
| HFNU | 2026 | `SRC-HFNU-2026-DG` | parsed_text | 2129 | `5ba90ae2b789eb7a8300bea553534226548652d57d8f18127a12225bd4e9d721` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-DG_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG_parsed.txt` |
| HFNU | 2026 | `SRC-HFNU-2026-DG` | document | 142514 | `c2c07f514d5b3326603dfe294290ed504a2218a4888f6d7a207c1741ad70c7fb` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-DG-ATT-02.pdf` | migrate | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG-EMBEDDED.pdf` |
| HFNU | 2024 | `SRC-HFNU-2024-BMRS` | html_snapshot | 37063 | `a1a60d37febbd8383dc3d066d5e92b18eebc07936af4a82ed16c4d5f69d7d45d` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-BMRS.html` | migrate | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-BMRS.html` |
| HFNU | 2024 | `SRC-HFNU-2024-BMRS` | parsed_text | 3046 | `39d2c150c87612fc42db82adca54653e15b715cdd943c684e3db216a04ae88a9` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-BMRS_parsed.txt` | migrate | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-BMRS_parsed.txt` |
| AHUA | 2024 | `SRC-AHUA-2024-ZYGG` | html_snapshot | 17508 | `7aba86bddd8515db405b3a598d0d5d691190dae109ebfce707da9e628f00c305` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZYGG.html` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZYGG.html` |
| AHUA | 2024 | `SRC-AHUA-2024-ZYGG` | parsed_text | 944 | `c2cd962eecea13db635b0dfd8ae6ab3f4a42b19c9f1466eddffef01dedd3868d` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZYGG_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZYGG_parsed.txt` |
| AHUA | 2024 | `SRC-AHUA-2024-ZC` | parsed_text | 28116 | `c4e2a78568a64a695e9d1a0382744392250ac1eff97b67e8fffbd70b464a071d` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC_parsed.txt` |
| AHUA | 2024 | `SRC-AHUA-2024-KSNR` | html_snapshot | 28237 | `aa69c1244ace8df41188ebdcf739f6431974072762abfc3365e1959c8ec96094` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-KSNR.html` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-KSNR.html` |
| AHUA | 2024 | `SRC-AHUA-2024-KSNR` | parsed_text | 2145 | `a7e9e266c49ccbf83dd2a600a67ad5bb7bc80ee65445fedcf43d146e2d61db5e` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-KSNR_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-KSNR_parsed.txt` |
| AHUA | 2024 | `SRC-AHUA-2024-LQ` | parsed_text | 1728 | `1f1a75ad873c22b4c10b5abfa8d96bb53a68b47e8dc8e8a44293e2f7f0853bb9` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-LQ_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-LQ_parsed.txt` |
| AHUA | 2024 | `SRC-AHUA-2024-BKRS` | parsed_text | 675 | `153a100b09f6af8a7b9d2bd3dc776c789869fd3ffdc9cebbc203a53eb97e4811` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-BMRS_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-BKRS_parsed.txt` |
| AHUA | 2025 | `SRC-AHUA-2025-FA` | html_snapshot | 28388 | `cb5c7c3b39edc2ac2bbe1ee2366c857adc5963ceaa940f9bdacb860ea13752d6` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-YG.html` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-FA.html` |
| AHUA | 2025 | `SRC-AHUA-2025-FA` | parsed_text | 3828 | `8c76741ea4658e8cc40e9abf8fd833cbc25a31e95ab047463bbeca081a8f9c54` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-YG_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-FA_parsed.txt` |
| AHUA | 2025 | `SRC-AHUA-2025-ZC` | html_snapshot | 194030 | `2478d991ede14f79335cc92dd8f2523e6a3bc073802be24ce7eb87dce5885078` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-ZC.html` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-ZC.html` |
| AHUA | 2025 | `SRC-AHUA-2025-ZC` | parsed_text | 28220 | `9eddb4c817c967e41a9ed0e2ede00ced1a82f4d6f32d1c5c5552dc90d053f20c` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-ZC_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-ZC_parsed.txt` |
| AHUA | 2025 | `SRC-AHUA-2025-ZC` | document | 13244 | `4e031e1a3f779b0d268c5fa0313ac470bce7da24047c180ce5ad4b48001731ef` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-ZC-ATT-01.docx` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-ZC-ATT-01.docx` |
| AHUA | 2025 | `SRC-AHUA-2025-ZC` | document | 18944 | `26d079d6170ced602e9b357b9d15d06ab5601d3b09f7bcb4c6e1822418ce30a8` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-ZC-ATT-02.doc` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-ZC-ATT-02.doc` |
| AHUA | 2025 | `SRC-AHUA-2025-KSNR` | html_snapshot | 27727 | `076ed1257b80c6965b8cf6f60d1358357a58bc5f86f8d9731082b09efd8e51ae` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-KSNR.html` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-KSNR.html` |
| AHUA | 2025 | `SRC-AHUA-2025-KSNR` | parsed_text | 2157 | `c90af9eb06f1cc1533c0581cc7118e433db0eda365c7340f7e27ccb0c87d0b56` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-KSNR_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-KSNR_parsed.txt` |
| AHUA | 2025 | `SRC-AHUA-2025-LQ` | html_snapshot | 31452 | `65c3bb764ca9e66cb942cb6bf4fb9e26fb4cda6ed9b4a6d69f30c3f11b195df2` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-LQ.html` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-LQ.html` |
| AHUA | 2025 | `SRC-AHUA-2025-LQ` | parsed_text | 1564 | `b1c34857bd28f7f58f6058a4856b853671538bfb821174d650731666cd906cae` | `evidence/stage1/raw/2025/AHUA/DOC-AHUA-2025-LQ_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2025/DOC-AHUA-2025-LQ_parsed.txt` |
| AHUA | 2026 | `SRC-AHUA-2026-FA` | parsed_text | 3829 | `bb8ca4cf984b9153fc0c40068e0bfd17de66252077aca65b6d4dcb3076c850e7` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-YG_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-FA_parsed.txt` |
| AHUA | 2026 | `SRC-AHUA-2026-XZYX` | parsed_text | 2456 | `2f51bd684bcc177bf634c0491fddf4464124678466bcb4a991b7b436d405ed91` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-XZ_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-XZYX_parsed.txt` |
| AHUA | 2026 | `SRC-AHUA-2026-ZC` | parsed_text | 29426 | `e61b361dc2067c58d8ff04454eee327fab477cd5395ae7b293ce3ad8a513cb06` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC_parsed.txt` |
| AHUA | 2026 | `SRC-AHUA-2026-KSNR` | parsed_text | 2554 | `5d9ad9a1116c2e7a262903afb664181a7d5c5e86e7d6cbb460c5c2ab162e17e9` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-KSNR_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-KSNR_parsed.txt` |
| AHUA | 2026 | `SRC-AHUA-2026-LQ` | parsed_text | 1636 | `1c950d65ec065a33fbffa8e3f9381ef23c9163013429af7890cdd288199cae1b` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-LQ_parsed.txt` | migrate | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-LQ_parsed.txt` |

## 仅 PR #3 存在

| 学校 | 年份 | Source | 类型 | 大小 | SHA-256 | 路径 | 原因 |
|---|---:|---|---|---:|---|---|---|
| HFNU | 2024 | `SRC-HFNU-2024-DG` | parsed_text | 81462 | `1e1041055abe41f0e7ea61582220cbfc6bc4dc458a25e76256ffc128892c70f1` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-DG.txt` | PR #3 独有的 pdftotext 解析文本；PR #2 只保存对应 PDF 原件。 |
| HFNU | 2025 | `SRC-HFNU-2025-DG` | parsed_text | 71011 | `446590f90d08e1e8cd8ebd47331a583e5166376b621ac73744ed023e39ecae88` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-DG.txt` | PR #3 独有的 pdftotext 解析文本；PR #2 只保存对应 PDF 原件。 |
| HFNU | 2026 | `SRC-HFNU-2026-DG` | parsed_text | 69751 | `47d1c75f745f681c63d7c7a26ba7127c787d4e839bffb2b5343baa03e7b43ac2` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG.txt` | PR #3 独有的 pdftotext 解析文本；PR #2 只保存对应 PDF 原件。 |

## 两个 PR 内容相同

| 学校 | 年份 | Source | 大小 | SHA-256 | PR #2 路径 | PR #3 路径 |
|---|---:|---|---:|---|---|---|
| HFNU | 2024 | `SRC-HFNU-2024-ZC` | 80553 | `287a0ad40dd786ed6ba0f85f735677232b1e636e90a1b0ab15a3949e348176a5` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC.html` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC.html` |
| HFNU | 2024 | `SRC-HFNU-2024-ZC` | 13992 | `61e2d59ba37638de7b08f5c966b45528c87b1204dcfcfde1ee62bb2141875209` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC-ATT-01.doc` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC-ATT-01.docx` |
| HFNU | 2024 | `SRC-HFNU-2024-ZC` | 125855 | `03cce76fbdab1dbb75634f3b5518e899f008f5d2c65c682099007ebe31d4ea78` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC-ATT-02.doc` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC-ATT-02.docx` |
| HFNU | 2024 | `SRC-HFNU-2024-LQ` | 48438 | `5d7c3b001fdd413ef78c2627b655f66e4c807630ef5fef9a7931d7c8c56f41e8` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-LQ.html` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-LQ.html` |
| HFNU | 2025 | `SRC-HFNU-2025-LQ` | 117971 | `af0d182d21e6daccf20fb8c9e6bbc2d261d858978bb665977299095974ad9bb7` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-LQ.html` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-LQ.html` |
| HFNU | 2026 | `SRC-HFNU-2026-LQ` | 23355 | `09f1d78c5d0e37bce0c33cfc023aca00867fab2d98f5353c34d164409839b48e` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-LQ.html` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-LQ.html` |
| HFNU | 2024 | `SRC-HFNU-2024-DG` | 69850 | `a69a1381e8f886276c5c58872c30bbf89369e95ba48fff5485e57c1291394a84` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-DG.html` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-DG.html` |
| HFNU | 2024 | `SRC-HFNU-2024-DG` | 651452 | `e15ca0acedf1f871dc144c69f83e5c6456873f309be7ccc1e8e48888f8cc1e75` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-DG-ATT-01.pdf` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-DG.pdf` |
| HFNU | 2025 | `SRC-HFNU-2025-DG` | 51098 | `e0bdd2547fd2ff96801ee3b362c57732a2501a5f0f3d280e4a2505fdf4366676` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-DG.html` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-DG.html` |
| HFNU | 2025 | `SRC-HFNU-2025-DG` | 586659 | `1e1b59b9e6436bc291a3ab42d02ff77ba4aaa5aed676216f1a498d0de2c0200c` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-DG-ATT-01.pdf` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-DG.pdf` |
| HFNU | 2026 | `SRC-HFNU-2026-DG` | 24692 | `a545bb070d42c2b120f2d118ff34c1208a4d96f4f1785a98ae7a76ff3ed03ca1` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-DG.html` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG.html` |
| HFNU | 2026 | `SRC-HFNU-2026-DG` | 615279 | `7c1249bea15940d848a540993ed9bbb5ea252097af2472f1729d48b391ff2559` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-DG-ATT-01.pdf` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG.pdf` |
| AHUA | 2024 | `SRC-AHUA-2024-ZC` | 183815 | `1826b4409a378d5f9e30645c49697976ed4a780a8415da675e78def2ce656df1` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC.html` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC.html` |
| AHUA | 2024 | `SRC-AHUA-2024-ZC` | 218980 | `4e6eab8b0a671ab67d65e7b188a6e662b0f55b87f20439a12958a7fdcdaec53a` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC-ATT-01.pdf` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC-ATT-01.pdf` |
| AHUA | 2024 | `SRC-AHUA-2024-ZC` | 479873 | `64883bc9171357c13cdca15294b6e5915c810ec990e2a21c9675715fc4220536` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC-ATT-02.pdf` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC-ATT-02.pdf` |
| AHUA | 2024 | `SRC-AHUA-2024-LQ` | 28450 | `9f81369b86bc619f0a639e781163c73a65cd5f63fdb10dfa1d3268f5c2d4e451` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-LQ.html` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-LQ.html` |
| AHUA | 2024 | `SRC-AHUA-2024-BKRS` | 18792 | `428ed654972141ce2f002322448095884d75123eadf99c26891c8eeedd7b3ff0` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-BMRS.html` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-BKRS.html` |
| AHUA | 2026 | `SRC-AHUA-2026-FA` | 28784 | `c29020a0e115d949aef17c2218334f055bb741fda4251628dc912b2c42ec01d4` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-YG.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-FA.html` |
| AHUA | 2026 | `SRC-AHUA-2026-XZYX` | 36031 | `09a155557821b9cce1ee784af9246bc01ab5e1b921c763caad84490bc3b75b65` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-XZ.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-XZYX.html` |
| AHUA | 2026 | `SRC-AHUA-2026-ZC` | 216504 | `70cdd25610d5d8dc35865e177fa1262da8662bd32c91e646e55c1e950b7a3f15` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC.html` |
| AHUA | 2026 | `SRC-AHUA-2026-ZC` | 13254 | `db2a0e413d98a0406ee68426a0629f83e55d40c09808fe36460fb939ef0a324b` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC-ATT-01.docx` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC-ATT-01.docx` |
| AHUA | 2026 | `SRC-AHUA-2026-ZC` | 19456 | `23bc0bed7a7afa4d6bda370dafaaa1c720a03fad8edaf91518a309a9769de8b2` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC-ATT-02.doc` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC-ATT-02.doc` |
| AHUA | 2026 | `SRC-AHUA-2026-KSNR` | 33756 | `b40d785871b1b5eae198bc24bf10366a71a6a69f2a9cbb73a66d4375e8c3d26e` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-KSNR.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-KSNR.html` |
| AHUA | 2026 | `SRC-AHUA-2026-LQ` | 33204 | `1f7c18787de23560863575b5746a6db61542270b22e7181908c80be2340323c5` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-LQ.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-LQ.html` |

## URL 相同但文件哈希不同

| URL | PR #2 类型 / SHA | PR #3 类型 / SHA | 阻塞 | 解释 |
|---|---|---|---:|---|
| `https://zsb.hfnu.edu.cn/info/1003/2715.htm` | parsed_text / `d7a6c2d2891bfe150ee5b26eb95a434cac3e6ba2f1673a6b15537a272a4d350c` | html_snapshot / `287a0ad40dd786ed6ba0f85f735677232b1e636e90a1b0ab15a3949e348176a5` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/info/1002/3065.htm` | parsed_text / `92da5bc14c5d7f4bad7fef4b24a72f091a12bc234f77663773e8565be75ed65c` | html_snapshot / `5d7c3b001fdd413ef78c2627b655f66e4c807630ef5fef9a7931d7c8c56f41e8` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/info/1002/3475.htm` | parsed_text / `6ce5faa25d110c659794d11848392cb2c52ad6e39da9081763fea05129c4512a` | html_snapshot / `af0d182d21e6daccf20fb8c9e6bbc2d261d858978bb665977299095974ad9bb7` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/info/1002/3885.htm` | parsed_text / `7fc2629c23dccf3ef767e2db8ae3f1d79f4e4dc16f66e8b22d890882eab592bf` | html_snapshot / `09f1d78c5d0e37bce0c33cfc023aca00867fab2d98f5353c34d164409839b48e` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/info/1002/2695.htm` | parsed_text / `f94ec9a6e060cf6b3bb40013e13394d71ac49c3683a9c4d0b40d9b37849b8d7a` | html_snapshot / `a69a1381e8f886276c5c58872c30bbf89369e95ba48fff5485e57c1291394a84` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/info/1002/3215.htm` | parsed_text / `4af53aab6497776f3da040bbacbefd25bcf0e0dc09f63aed30d58608127f9f8a` | html_snapshot / `e0bdd2547fd2ff96801ee3b362c57732a2501a5f0f3d280e4a2505fdf4366676` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/info/1002/3625.htm` | parsed_text / `5ba90ae2b789eb7a8300bea553534226548652d57d8f18127a12225bd4e9d721` | html_snapshot / `a545bb070d42c2b120f2d118ff34c1208a4d96f4f1785a98ae7a76ff3ed03ca1` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2024/0321/c201a29345/page.htm` | parsed_text / `c4e2a78568a64a695e9d1a0382744392250ac1eff97b67e8fffbd70b464a071d` | html_snapshot / `1826b4409a378d5f9e30645c49697976ed4a780a8415da675e78def2ce656df1` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2024/0524/c201a31068/page.htm` | parsed_text / `1f1a75ad873c22b4c10b5abfa8d96bb53a68b47e8dc8e8a44293e2f7f0853bb9` | html_snapshot / `9f81369b86bc619f0a639e781163c73a65cd5f63fdb10dfa1d3268f5c2d4e451` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2024/0406/c201a29560/page.htm` | parsed_text / `153a100b09f6af8a7b9d2bd3dc776c789869fd3ffdc9cebbc203a53eb97e4811` | html_snapshot / `428ed654972141ce2f002322448095884d75123eadf99c26891c8eeedd7b3ff0` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2025/1031/c201a44096/page.htm` | parsed_text / `bb8ca4cf984b9153fc0c40068e0bfd17de66252077aca65b6d4dcb3076c850e7` | html_snapshot / `c29020a0e115d949aef17c2218334f055bb741fda4251628dc912b2c42ec01d4` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2026/0205/c201a45646/page.htm` | parsed_text / `2f51bd684bcc177bf634c0491fddf4464124678466bcb4a991b7b436d405ed91` | html_snapshot / `09a155557821b9cce1ee784af9246bc01ab5e1b921c763caad84490bc3b75b65` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2026/0318/c201a46012/page.htm` | parsed_text / `e61b361dc2067c58d8ff04454eee327fab477cd5395ae7b293ce3ad8a513cb06` | html_snapshot / `70cdd25610d5d8dc35865e177fa1262da8662bd32c91e646e55c1e950b7a3f15` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2026/0318/c201a46013/page.htm` | parsed_text / `5d9ad9a1116c2e7a262903afb664181a7d5c5e86e7d6cbb460c5c2ab162e17e9` | html_snapshot / `b40d785871b1b5eae198bc24bf10366a71a6a69f2a9cbb73a66d4375e8c3d26e` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://www.ahua.edu.cn/zsw/2026/0520/c201a46973/page.htm` | parsed_text / `1c950d65ec065a33fbffa8e3f9381ef23c9163013429af7890cdd288199cae1b` | html_snapshot / `1f7c18787de23560863575b5746a6db61542270b22e7181908c80be2340323c5` | 否 | 同一官方页面的派生文本与原始 HTML 使用相同 source_url；文件类型不同，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/system/_content/download.jsp?owner=1090424591&urltype=news.DownloadAttachUrl&wbfileid=A5E8FF4D6F6748DEA5F8A94725163309` | document / `e15ca0acedf1f871dc144c69f83e5c6456873f309be7ccc1e8e48888f8cc1e75` | parsed_text / `1e1041055abe41f0e7ea61582220cbfc6bc4dc458a25e76256ffc128892c70f1` | 否 | PR #2 保存官方 PDF 原件，PR #3 额外保存 pdftotext 派生文本；同一来源 URL、不同表示，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/system/_content/download.jsp?owner=1090424591&urltype=news.DownloadAttachUrl&wbfileid=1712D2B6AD8613B7DB1A57B008224FC0` | document / `1e1b59b9e6436bc291a3ab42d02ff77ba4aaa5aed676216f1a498d0de2c0200c` | parsed_text / `446590f90d08e1e8cd8ebd47331a583e5166376b621ac73744ed023e39ecae88` | 否 | PR #2 保存官方 PDF 原件，PR #3 额外保存 pdftotext 派生文本；同一来源 URL、不同表示，哈希不同属于预期。 |
| `https://zsb.hfnu.edu.cn/system/_content/download.jsp?owner=1090424591&urltype=news.DownloadAttachUrl&wbfileid=7298453E08C33B075C74A9629F539E8D` | document / `7c1249bea15940d848a540993ed9bbb5ea252097af2472f1729d48b391ff2559` | parsed_text / `47d1c75f745f681c63d7c7a26ba7127c787d4e839bffb2b5343baa03e7b43ac2` | 否 | PR #2 保存官方 PDF 原件，PR #3 额外保存 pdftotext 派生文本；同一来源 URL、不同表示，哈希不同属于预期。 |

## 文件哈希相同但路径不同

| Source | SHA-256 | PR #2 路径 | PR #3 路径 | 原因 |
|---|---|---|---|---|
| `SRC-HFNU-2024-ZC` | `287a0ad40dd786ed6ba0f85f735677232b1e636e90a1b0ab15a3949e348176a5` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC.html` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2024-ZC` | `61e2d59ba37638de7b08f5c966b45528c87b1204dcfcfde1ee62bb2141875209` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC-ATT-01.doc` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC-ATT-01.docx` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2024-ZC` | `03cce76fbdab1dbb75634f3b5518e899f008f5d2c65c682099007ebe31d4ea78` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-ZC-ATT-02.doc` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-ZC-ATT-02.docx` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2024-LQ` | `5d7c3b001fdd413ef78c2627b655f66e4c807630ef5fef9a7931d7c8c56f41e8` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-LQ.html` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-LQ.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2025-LQ` | `af0d182d21e6daccf20fb8c9e6bbc2d261d858978bb665977299095974ad9bb7` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-LQ.html` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-LQ.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2026-LQ` | `09f1d78c5d0e37bce0c33cfc023aca00867fab2d98f5353c34d164409839b48e` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-LQ.html` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-LQ.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2024-DG` | `a69a1381e8f886276c5c58872c30bbf89369e95ba48fff5485e57c1291394a84` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-DG.html` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-DG.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2024-DG` | `e15ca0acedf1f871dc144c69f83e5c6456873f309be7ccc1e8e48888f8cc1e75` | `evidence/stage1/raw/2024/HFNU/DOC-HFNU-2024-DG-ATT-01.pdf` | `evidence/pilot_a/HFNU/2024/DOC-HFNU-2024-DG.pdf` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2025-DG` | `e0bdd2547fd2ff96801ee3b362c57732a2501a5f0f3d280e4a2505fdf4366676` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-DG.html` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-DG.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2025-DG` | `1e1b59b9e6436bc291a3ab42d02ff77ba4aaa5aed676216f1a498d0de2c0200c` | `evidence/stage1/raw/2025/HFNU/DOC-HFNU-2025-DG-ATT-01.pdf` | `evidence/pilot_a/HFNU/2025/DOC-HFNU-2025-DG.pdf` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2026-DG` | `a545bb070d42c2b120f2d118ff34c1208a4d96f4f1785a98ae7a76ff3ed03ca1` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-DG.html` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-HFNU-2026-DG` | `7c1249bea15940d848a540993ed9bbb5ea252097af2472f1729d48b391ff2559` | `evidence/stage1/raw/2026/HFNU/DOC-HFNU-2026-DG-ATT-01.pdf` | `evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG.pdf` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2024-ZC` | `1826b4409a378d5f9e30645c49697976ed4a780a8415da675e78def2ce656df1` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC.html` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2024-ZC` | `4e6eab8b0a671ab67d65e7b188a6e662b0f55b87f20439a12958a7fdcdaec53a` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC-ATT-01.pdf` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC-ATT-01.pdf` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2024-ZC` | `64883bc9171357c13cdca15294b6e5915c810ec990e2a21c9675715fc4220536` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-ZC-ATT-02.pdf` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-ZC-ATT-02.pdf` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2024-LQ` | `9f81369b86bc619f0a639e781163c73a65cd5f63fdb10dfa1d3268f5c2d4e451` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-LQ.html` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-LQ.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2024-BKRS` | `428ed654972141ce2f002322448095884d75123eadf99c26891c8eeedd7b3ff0` | `evidence/stage1/raw/2024/AHUA/DOC-AHUA-2024-BMRS.html` | `evidence/pilot_b/AHUA/2024/DOC-AHUA-2024-BKRS.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-FA` | `c29020a0e115d949aef17c2218334f055bb741fda4251628dc912b2c42ec01d4` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-YG.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-FA.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-XZYX` | `09a155557821b9cce1ee784af9246bc01ab5e1b921c763caad84490bc3b75b65` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-XZ.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-XZYX.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-ZC` | `70cdd25610d5d8dc35865e177fa1262da8662bd32c91e646e55c1e950b7a3f15` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-ZC` | `db2a0e413d98a0406ee68426a0629f83e55d40c09808fe36460fb939ef0a324b` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC-ATT-01.docx` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC-ATT-01.docx` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-ZC` | `23bc0bed7a7afa4d6bda370dafaaa1c720a03fad8edaf91518a309a9769de8b2` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-ZC-ATT-02.doc` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-ZC-ATT-02.doc` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-KSNR` | `b40d785871b1b5eae198bc24bf10366a71a6a69f2a9cbb73a66d4375e8c3d26e` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-KSNR.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-KSNR.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |
| `SRC-AHUA-2026-LQ` | `1f7c18787de23560863575b5746a6db61542270b22e7181908c80be2340323c5` | `evidence/stage1/raw/2026/AHUA/DOC-AHUA-2026-LQ.html` | `evidence/pilot_b/AHUA/2026/DOC-AHUA-2026-LQ.html` | 字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，部分扩展名按文件魔数纠正。 |

## 疑似网站公共资源

| SHA-256 | 来源页数 | 文件数 | URL | 决策 |
|---|---:|---:|---|---|
| `269a812c4520e556b64e5696340556234a57b61bc5022d6efd4f12b389f75406` | 14 | 14 | `https://www.ahua.edu.cn/_upload/article/images/70/82/251002284a64a5f1a5e7deb822d8/645c76d2-1b74-4e8d-9e91-0dd5f0820e93_s.png` | 不迁移 |
| `368b9d72f073234c79da26918369dcd2a1fe046877f6bb6f2ca6df26ddc23099` | 14 | 14 | `https://www.ahua.edu.cn/_upload/article/images/d9/91/0ec8c52443c1ab52eaa53f0e9560/0e84734a-6349-41c6-865d-3fa2958db280_s.jpg` | 不迁移 |

## 疑似无关附件

| 学校 | 年份 | Source | 类型 | 大小 | SHA-256 | PR #2 路径 | 原因 |
|---|---:|---|---|---:|---|---|---|

## Gate 0 决策

- 迁移 AHUA 2025 材料、AHUA 2024 招生专业公告和考试内容、HFNU 2024 报名人数、HTML 解析文本及两个页面内嵌 PDF。
- 迁移经隐私复核的 AHUA 2025 两个官方空白申请/承诺表；继续排除 28 个站点公共图片。
- 保留 PR #3 独有的 HFNU 2024—2026 三个 PDF 解析文本。
- 收敛后仅支持 `scripts/collect_stage1_evidence.py`，且只能写入 `evidence/`。

## 非变更范围

- 未修改 Schema、staging、normalized、SQLite、canonical raw 或业务事实。
