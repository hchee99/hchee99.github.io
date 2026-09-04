# JLPT Quiz Data Notice

이 문서는 `openjlpt-data.js`에 포함된 확장 어휘 데이터의 출처, 변경 내용,
라이선스를 설명합니다. 앱의 기존 수기 입력 데이터와 프로그램 코드 전체에
동일한 라이선스를 선언하는 문서가 아니라, 아래 파생 데이터에 대한 고지입니다.

## OpenJLPT 파생 데이터

- 원본: [OpenJLPT](https://github.com/evanclan/OpenJLPT)
- 사용한 원본 리비전: `c42fd9fa3777bfc1775446f7c418d549dfd6e4cf`
- 라이선스: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)
- 이 프로젝트의 파생 파일: `openjlpt-data.js`

OpenJLPT 어휘·읽기·JLPT 레벨·일본어/영어 예문에서 기존 앱에 없는 항목을
선별했습니다. 복합 표기, 구분자가 들어간 항목, 읽기 형식이 비정상인 항목과 중복 항목은
제외했습니다. 영문 뜻과 영어 예문은 한국어로 기계 번역했으며, 문맥 없이
오역되기 쉬운 일부 뜻과 예문은 별도의 검토된 한국어 값으로 바로잡았습니다.
이후 필수 필드, 언어, 중복, 예문 포함 관계를 자동 검증했습니다. 적절한 원본 예문이 없는
항목에는 해당 표기를 직접 포함하는 중립적인 학습용 예문을 추가했습니다.

이 파생 데이터는 원본과 같은 **CC BY-SA 4.0** 조건으로 제공합니다. 재배포하거나
수정할 경우 OpenJLPT와 아래 원천 자료를 표시하고, 라이선스 링크를 제공하며,
파생 데이터에도 동일한 라이선스를 적용해야 합니다.

커밋된 `openjlpt-data.js`가 배포용 기준 데이터입니다. 같은 원본 리비전으로
다시 생성할 때는 이 파일의 검증된 한국어 번역을 우선 재사용하고, 새 항목에만
외부 번역을 요청합니다.

## OpenJLPT의 원천 자료

OpenJLPT의 [NOTICE](https://github.com/evanclan/OpenJLPT/blob/c42fd9fa3777bfc1775446f7c418d549dfd6e4cf/NOTICE.md)에 따라 다음 출처를 표시합니다.

| 출처 | 사용 분야 | 라이선스 |
|---|---|---|
| [JMdict / EDICT — EDRDG](https://www.edrdg.org/) | 어휘 읽기와 영문 뜻 | CC BY-SA 4.0 |
| [KANJIDIC2 — EDRDG](https://www.edrdg.org/wiki/KANJIDIC_Project.html) | 한자 정보 | CC BY-SA 4.0 |
| [Jonathan Waller's JLPT Resources](https://www.tanos.co.uk/jlpt/) | N5~N1 레벨 분류 | CC BY |
| [Tatoeba](https://tatoeba.org/) | 일본어·영어 예문 | [CC BY 2.0 FR](https://creativecommons.org/licenses/by/2.0/fr/) |

JLPT 주관 기관은 공식 급수별 단어 목록을 공개하지 않으므로, 이 데이터의 급수
분류는 Jonathan Waller의 커뮤니티 목록을 바탕으로 한 비공식 학습용 분류입니다.

## 한자 훈음 보완 데이터

신규 단어의 한자 훈음 중 기존 사전에 없던 항목은
[libhangul](https://github.com/libhangul/libhangul)의 `data/hanja/hanja.txt`
(리비전 `a34aef73378c0992316861bbf13fc914ee7577d9`)에서 가져왔습니다.

Copyright (c) 2005, 2006 Choe Hwanjin. All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list
   of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this
   list of conditions and the following disclaimer in the documentation and/or other
   materials provided with the distribution.
3. Neither the name of the author nor the names of contributors may be used to endorse
   or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
