"""Reviewed changes layered over the immutable Open Dictionary v2.0 archive.

Chinese definitions and examples below are original editorial paraphrases.
No network or model calls happen when these records are built or displayed.
"""
SOURCE = 'https://www.collinsdictionary.com/dictionary/english/'

def sense(pos, gloss, text, en='', zh='', usage='', priority='core', **extra):
    return dict(pos=pos, gloss=gloss, definition=text, priority=priority,
        examples=[{'text':en,'translation':zh}] if en else [],
        usage=usage, verified_usage=bool(usage), labels=[], topics=[], proper=False, **extra)

def entry(summary, senses, reference, **extra):
    return dict(overview=summary, senses=senses, references=[reference], reviewed_segments=True, **extra)

ADDITIONS = {
 'although':entry('although 表示“虽然、尽管”：先承认一个事实，再说明另一件仍然成立、可能出乎意料的事。',[
    sense('conj','虽然；尽管','引出一个与主句形成转折的事实。比如“虽然下雨，我们还是出去了”，下雨并没有阻止后面的事。',
        'Although it was raining, we went for a walk.','虽然在下雨，我们还是出去散步了。')],SOURCE+'although'),
 'unless':entry('unless 表示“除非……，否则……”：某件事通常会发生，只有后面那个条件成立时才例外。',[
    sense('conj','除非；如果不','引出使前面或后面的说法出现例外的条件。I will go unless it rains 就是“如果不下雨，我就去”。',
        'We will leave at eight unless you call.','除非你打电话来，否则我们八点出发。')],SOURCE+'unless'),
 'albeit':entry('albeit 表示“尽管、虽然”，常在一句话中补充一个让步或限制，语气偏书面。',[
    sense('conj','尽管；虽然','先说某事成立，再补充它有一个不完全理想的方面；常接简短的形容词、副词或短语。',
        'The plan worked, albeit slowly.','这个方案奏效了，尽管进展缓慢。')],SOURCE+'albeit'),
 'anymore':entry('anymore 常与否定表达连用，表示过去会发生的事现在“不再”发生；英式英语通常写作 any more。',[
    sense('adv','不再','表示从前存在的行为或情况已经停止，常见于 not ... anymore。',
        'I do not live there anymore.','我已经不住在那里了。')],SOURCE+'anymore'),
 "n't":entry("n't 是 not 在 don't、isn't、can't 等否定缩略形式中的写法，表示“不、没有”。",[
    sense('adv','不；没有','它用于助动词或情态动词的否定缩略形式，例如 do not 可缩写为 don’t。',
        "I don't know.",'我不知道。')],'https://en.wiktionary.org/wiki/n%27t'),
 'startle':entry('startle 指某个突然、意外的声音或事情使人“吓一跳、吃一惊”，侧重瞬间的反应。',[
    sense('verb','使吓一跳','让人因意外的动静突然吃惊，往往还带一点惊吓。',
        'The sudden noise startled me.','突然的响声吓了我一跳。')],SOURCE+'startle',forms=['startles','startled','startling']),
 'fascinate':entry('fascinate 指某人或某事极有吸引力，使人很感兴趣、看得或想得入迷。',[
    sense('verb','使着迷','引起并牢牢吸引一个人的兴趣，让他很想继续看、听或了解。',
        'Stories about space fascinate her.','关于太空的故事让她着迷。')],SOURCE+'fascinate',forms=['fascinates','fascinated','fascinating']),
 'entitle':entry('entitle 常见的意思有两个：使人有权获得某物或做某事；给书、文章等起标题。',[
    sense('verb','使有权；使有资格','某种身份、规定或条件使一个人有权得到某物，或有资格做某事。',
        'This ticket entitles you to a free drink.','凭这张票，你可以免费领取一杯饮料。'),
    sense('verb','给……命名；给……题名','给书、文章、电影等作品起一个名称，常见于 be entitled 后接标题。',
        'The article is entitled A New Beginning.','这篇文章的标题是《新的开始》。')],SOURCE+'entitle',forms=['entitles','entitled','entitling']),
 'footstep':entry('footstep 指走路时迈出的一步，也常指脚步落地的声音；footsteps 经常用复数。',[
    sense('noun','脚步；脚步声','走路迈出的一步，或走路时发出的声音。',
        'I heard footsteps behind me.','我听见身后有脚步声。')],SOURCE+'footstep',forms=['footsteps']),
 'fingertip':entry('fingertip 是手指最末端的部分，也就是指尖。',[
    sense('noun','指尖','手指末端用于触摸东西的部位。',
        'She touched the glass with her fingertips.','她用指尖碰了碰玻璃。')],SOURCE+'fingertip',forms=['fingertips']),
 'policymaker':entry('policymaker 指参与制定政策、决定机构或政府采取什么做法的人。',[
    sense('noun','政策制定者','负责制定政策或决定行动方向的人，常指政府、组织中的决策人员。',
        'Policymakers are discussing the proposal.','政策制定者们正在讨论这项提议。')],SOURCE+'policymaker',forms=['policymakers']),
 'pollutant':entry('pollutant 指进入空气、水或土壤后造成污染的物质。',[
    sense('noun','污染物','使环境变脏、有害或不适宜生存的物质。',
        'The filter removes pollutants from the water.','这个过滤器能去除水中的污染物。')],SOURCE+'pollutant',forms=['pollutants']),
 'underlie':entry('underlie 指处在某物下面，也常用来表示“构成某事的基础”或“是背后的原因”。',[
    sense('verb','构成基础；是背后的原因','某个事实、想法或原因支撑着表面看到的现象，帮助解释它为什么会发生。',
        'Several assumptions underlie this argument.','这个论点建立在几个假设之上。'),
    sense('verb','位于……下面','处于某物的下方，常用来描述岩层、地面等的上下位置。',
        'Clay underlies the sandy soil.','沙质土壤下面是黏土。')],SOURCE+'underlie',forms=['underlies','underlay','underlain','underlying']),
 'devastate':entry('devastate 指严重破坏一个地方，也可指让一个人受到极大的打击、难过得难以承受。',[
    sense('verb','严重破坏','对一个地方或事物造成范围很大、后果严重的破坏。',
        'The flood devastated the town.','洪水严重破坏了这座城镇。'),
    sense('verb','使受到沉重打击','使人极其悲伤、震惊或失落。',
        'The news devastated her.','这个消息给了她沉重的打击。')],SOURCE+'devastate',forms=['devastates','devastated','devastating']),
 'accustom':entry('accustom 指使人逐渐习惯一种新的环境或做法，常见于 accustom yourself to。',[
    sense('verb','使习惯于','通过经历或练习，让原本陌生、不适应的事情变得熟悉。',
        'It took time to accustom myself to the noise.','我花了一段时间才习惯这里的噪声。')],SOURCE+'accustom',forms=['accustoms','accustomed','accustoming']),
 'situate':entry('situate 表示把某物放在特定位置，也可表示把某个观点或事件放到背景中理解；常见形式是 situated。',[
    sense('verb','使位于；把……置于','把事物安排在某个位置，或说明它所处的位置。',
        'The hotel is situated near the station.','这家酒店位于车站附近。')],SOURCE+'situate',forms=['situates','situated','situating']),
 'paralyze':entry('paralyze 指使身体或某个部位瘫痪、无法活动；也可比喻使人或事物因恐惧、混乱等无法行动或运转。',[
    sense('verb','使瘫痪；使无法行动','使身体失去活动能力，或让某人、某个系统受到严重阻碍而停滞。',
        'Fear paralyzed him.','恐惧让他动弹不得。')],SOURCE+'paralyze',forms=['paralyzes','paralyzed','paralyzing']),
}

# Spelling variants only: never map a verb such as fascinate to an adjective
# such as fascinated just because the latter happens to be in the source pack.
ALIASES = {'okay':'ok','afterward':'afterwards','utilize':'utilise','catalog':'catalogue',
    'characterise':'characterize','summarise':'summarize','postwar':'post-war',
    'watercolor':'watercolour','odour':'odor','cozy':'cosy','realisation':'realization',
    'reorganisation':'reorganization','paralyse':'paralyze'}

OVERVIEWS = {
 'field':'field 常指种植或放牧的一块土地、体育比赛的场地，以及某种工作或研究的领域。作动词时，field questions 表示回答、应对问题；还可表示接球或派出队员。',
 'bank':'bank 最常见的意思是“银行”和“河岸、湖岸”。作动词时，可指把钱存入银行、在某家银行办理业务，也可形容飞机侧倾转弯。银行与河岸应按不同用法分别理解。',
 'inform':'inform 常表示“告知、使了解”，也可以表示思想、经验或价值观对某事的内容和特点产生影响，即“影响、塑造”。be informed by 常可理解为“受……影响、以……为依据”。',
 'informed':'informed 作形容词，表示掌握了相关情况，或某个决定建立在充分了解之上。它也可能是 inform 的过去分词；be informed by 可表示“受……影响、以……为依据”。',
 'act':'act 作名词，常指一个行为，或戏剧中的“一幕”。作动词，常指采取行动、表现出某种行为，以及演戏、扮演角色。',
 'run':'run 最基本的意思是“跑”；也常指水等流动、机器或系统运转，以及经营、管理某项业务。不同搭配决定具体意思，例如 run a shop 是经营商店。',
 'subtle':'subtle 形容差别、变化或感觉细微、不容易察觉；也形容表达含蓄、手法精巧而不显眼。重点通常是“不明显，需要仔细体会”，不能一律译成“微妙”。',
 'sanguine':'sanguine 常表示对未来或结果乐观、有信心，语气偏正式。读到 be sanguine about 时，可先理解为“对……抱有乐观预期”；血红色等用法另列。',
 'ubiquitous':'ubiquitous 表示某种事物到处可见、广泛存在，语气通常比 common 更强；不一定要求它真的出现在每一个地方。',
 'credo':'credo 是个人或群体坚持并用来指导行为的信念、原则或信条，常用于谈人生观或政治理念。宗教中的信经及其音乐用法另列。',
}

# Selectors include part of speech and etymology: sense_id alone is not unique.
SENSE_PATCHES = {
 ('run','verb','et1','s1'):{'usage':'可以单独说 run，也可以接方向或路程，例如 run home、run to the station、run a mile。表示跑过一段距离时，后面可以直接接距离。','verified_usage':True},
 ('bank','noun','et1','s1'):{'definition':'指办理存款、贷款、转账等金融业务的银行机构，也可在具体语境中指人们去办理业务的银行场所。','usage':'常见搭配有 open an account at a bank、go to the bank。这里的 bank 可以指银行机构，也可以指具体网点。','verified_usage':True},
 ('bank','noun','et2','s1'):{'definition':'河流、湖泊或其他水道边缘的陆地，也就是水岸。','usage':'常见搭配有 on the bank of the river、along the river bank。','verified_usage':True},
 ('sanguine','adj','et1','s5'):{'usage':'常见搭配是 be sanguine about，表示对某事持乐观态度、有信心。这个词本身不保证这种乐观有充分根据，是否过于乐观仍须看上下文。','verified_usage':True},
 ('field','noun','et1','s9'):{'usage':'magnetic field、electric field 分别是磁场、电场。这里的物理“场”与研究或工作的“领域”是不同用法。','verified_usage':True},
 ('field','noun','et1','s11'):{'gloss':'电视扫描场','definition':'在隔行扫描的电视技术中，指构成一帧图像的一个扫描场；它不是完整的一帧图像。'},
}

FIELD_ADDITIONS = [
 sense('noun','领域；专业范围','某种工作、研究或活动所属的范围。例如 the field of medicine 指医学领域，an expert in her field 指她所在领域的专家。',
       'He works in the field of education.','他从事教育领域的工作。',sid='editorial-domain'),
 sense('adj','实地的；在现场进行的','形容研究或工作是在真实现场开展，而不是只在办公室、实验室或理论中进行。',
       'The students are doing field research.','学生们正在进行实地研究。',sid='editorial-fieldwork'),
]

# The upstream POS inventory omitted conjunctions. Restore the reading function
# explicitly, instead of showing only e.g. the rare noun sense of "if".
FUNCTION_WORDS = {
 'and':('和；并且','连接并列的人、事物或说法，表示把它们放在一起；连接动作时，也可能表示事情先后发生。','She opened the book and began to read.','她打开书，开始阅读。'),
 'or':('或者；否则','连接可供选择的事物或说法；在命令、建议之后，也可引出不这样做会产生的结果。','Hurry, or we will be late.','快点，否则我们会迟到。'),
 'but':('但是；而是','连接形成对照或转折的说法。not ... but ... 则表示“不是……而是……”。','The room is small but comfortable.','房间虽小，却很舒适。'),
 'if':('如果；是否','引出条件时表示“如果”；跟在 ask、know、wonder 等词后，也可引出“是否”这个问题。','I wonder if she is coming.','我想知道她会不会来。'),
 'because':('因为','引出原因，说明一件事为什么发生或一个判断为什么成立。','We stayed inside because it was raining.','因为在下雨，我们待在室内。'),
 'though':('虽然；尽管','承认一个事实，再说与它形成对照的情况。放在句末作副词时，也常表示“不过、可是”。','Though he was tired, he kept reading.','虽然累了，他还是继续读书。'),
 'so':('所以；因此','连接原因和结果，表示前面的情况导致后面的事。so that 常用来引出目的或结果。','It was getting dark, so we went home.','天快黑了，所以我们回家了。'),
 'as':('当……时；因为；正如','可引出同时发生的事、原因，或“照某种方式”进行的事。具体关系需要结合上下句判断。','As I was leaving, the phone rang.','我正要离开时，电话响了。'),
 'since':('自从；因为','引出起点时表示从过去某时一直到后来；说明理由时表示“既然、因为”。','Since you are here, we can begin.','既然你来了，我们就可以开始了。'),
 'while':('在……期间；而；虽然','可连接同时进行的事情，也可比较两种不同情况；有时表示让步，即“虽然”。','I read while she cooked.','她做饭时，我在看书。'),
 'that':('引出一个事实或说法','可把一个完整说法接到 think、say 等词后，通常不必单独译出。引出定语从句时，还可指代前面的事物或人。','I think that you are right.','我认为你是对的。'),
 'whether':('是否','引出存在两种或多种可能的情况，常见于 whether ... or ...，表示“是否……”或“不管是……还是……”。','I do not know whether to stay or leave.','我不知道该留下还是离开。'),
 'than':('比','引出比较的另一方，通常与 bigger、more、less 等比较表达连用。','She reads faster than I do.','她读得比我快。'),
 'until':('直到……才；一直到','表示某个时间是动作或状态持续的终点。not ... until ... 常表示直到那个时候某事才发生。','We waited until the rain stopped.','我们一直等到雨停了。'),
 'whereas':('而；然而','把两种不同或相反的情况并列起来，突出对照，常见于书面表达。','She likes tea, whereas I prefer coffee.','她喜欢茶，而我更喜欢咖啡。'),
 'before':('在……之前','引出一件比主句中的事情更晚发生的事，也就是主句的动作发生在它之前。','Check the address before you leave.','出发前检查一下地址。'),
 'after':('在……之后','引出较早发生的事，说明主句中的事情随后发生。','We talked after everyone had left.','大家都离开后，我们聊了聊。'),
 'when':('当……时','引出一个时间或情形，说明另一件事是在那时发生的。','Call me when you arrive.','你到了之后给我打电话。'),
 'once':('一旦；当……之后','引出一个条件或时间点，表示那件事发生后，后面的情况就会随之成立。','Once you start, it gets easier.','一旦开始，就会容易些。'),
 'for':('因为；由于','作连词时，在一个说法后补充原因或解释，常见于书面叙述；与介词 for 的“给、为了”等用法不同。','We stopped, for it was getting late.','我们停下了，因为时间已经很晚了。'),
 'yet':('然而；可是','作连词时连接带有转折的两个说法，后面的事常与前面的情况不太相称或出乎意料。','It was difficult, yet she did not give up.','事情很难，可她没有放弃。'),
 'nor':('也不','连接两个否定说法，常见于 neither ... nor ...，表示“既不……也不……”。','Neither Tom nor Anna was there.','汤姆和安娜都不在那里。'),
 'provided':('只要；条件是','provided 或 provided that 引出必须满足的条件；在该条件下，另一件事才被允许或可能发生。','You can borrow it provided that you return it tomorrow.','只要你明天归还，就可以借走。'),
 'lest':('以免；唯恐','引出想要避免的结果，语气正式或偏文学，常用于解释为什么要小心做某事。','He spoke quietly lest he wake the child.','他说话很轻，以免吵醒孩子。'),
 'whenever':('每当；无论何时','表示每次某种情况出现，或不管在什么时间，后面的说法都成立。','Visit whenever you like.','你想什么时候来就什么时候来。'),
 'wherever':('无论在哪里；到任何……地方','表示不管地点在哪里，或可以选择任何符合条件的地方。','Sit wherever you like.','你想坐哪里就坐哪里。'),
}

FUNCTION_OVERVIEWS = {
 'as':'as 常表示“作为”，也可连接句子，表示“当……时、因为、正如”。as ... as 用来作同等程度的比较；具体含义要看搭配。',
 'for':'for 常表示“给、为了”，也可表示一段时间或支持某人某事。作连词时，它可以补充原因，意思接近“因为”。',
 'so':'so 作副词常表示“这样、如此、这么”；连接两个说法时常表示“所以、因此”。so that 则常引出目的或结果。',
 'yet':'yet 作副词常与否定或疑问表达连用，表示到现在或所说的时间“还、尚未”；作连词表示“然而、可是”。',
 'that':'that 可以表示“那个”，也可引出前面的人或物的补充说明；跟在 think、say 等词后时，它连接一个完整说法，通常不必单独译出。',
 'since':'since 可表示从过去某时起一直持续，也可说明理由，表示“既然、因为”。要根据它引出的是时间还是原因来理解。',
 'while':'while 常表示一件事发生的期间，也可把两种情况放在一起作对照，表示“而”。作名词时，a while 表示“一段时间”。',
 'before':'before 表示时间上的“在……之前”，可接时间、动作或完整的句子；有时也表示位置或顺序上的“在……前面”。',
 'after':'after 常表示时间、顺序上的“在……之后”，也可表示跟在某人或某物后面。',
 'once':'once 常表示“一次”或“曾经”；连接句子时，可表示“一旦……、当……之后”。',
 'when':'when 询问时间时表示“什么时候”；连接句子时，常表示“当……时”。',
 'provided':'provided 可以是 provide 的过去式或过去分词，表示“提供了、被提供”；provided (that) 用来引出条件，表示“只要、条件是”。',
 'though':'though 常表示“虽然、尽管”；放在句末时，作副词可表示“不过、可是”，用来补充转折。',
}

def function_sense(word):
    gloss,text,en,zh=FUNCTION_WORDS[word]
    return sense('conj',gloss,text,en,zh,sid='editorial-conjunction',etymology='editorial',section='main')

REFERENCES = {w:[SOURCE+w] for w in set(OVERVIEWS)|{x[0] for x in SENSE_PATCHES}}
REFERENCES['run'].append('https://www.oxfordlearnersdictionaries.com/definition/english/mile')
REFERENCES['bank'].append('https://en.wiktionary.org/wiki/bank')

LICENSE_NOTICE = '''Open Dictionary v2.0 / Leaf corrected data edition 1
Source: https://github.com/ahpxex/open-dictionary/releases/tag/v2.0
Upstream: English Wiktionary contributors, extracted with Wiktextract.
License: Creative Commons Attribution-ShareAlike 4.0 International.
https://creativecommons.org/licenses/by-sa/4.0/
Changes by Leaf: structural validation, exact deduplication, presentation
classification, original Chinese editorial additions, reviewed sense patches,
spelling/form lookup repair. This derivative data is shared under CC BY-SA 4.0.
Original generated notes and the immutable source archive are retained in the
build inputs and audit records; unreviewed usage rules and memory hooks are not
presented as verified dictionary guidance. Whole-corpus semantic correctness
has not been established. No model or network is required for runtime lookup.
'''
