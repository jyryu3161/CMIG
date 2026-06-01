# cmig-search-ga Design (Option C)
| core/search_ga.py | 신규 | GAConfig·GAResult·genetic_search(+_tournament/_crossover/_mutate) |
| tests/test_search_ga.py | 신규 | 6 (합성 fitness·결정적) |
## 설계: genome=정렬 멤버셋. init random subset(size bounds). 세대: elitism→tournament 선택→union crossover(size 무작위)→mutation(add/remove). fitness_fn 주입·캐시(evaluations 노출). 결정적 random.Random(seed). 근사 경고 동반.
