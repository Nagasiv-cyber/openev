import sys
sys.path.insert(0, r'c:\Users\K.Visagan\Desktop\openev')
from environment import CodeReviewEnvironment

scenarios = [
    ('All Perfect (correct+severity+comment)', [
        ('REJECT','CRITICAL','SQL injection via string concat'),
        ('REJECT','HIGH','XSS via innerHTML'),
        ('REJECT','HIGH','Pickle deserialization'),
        ('REJECT','CRITICAL','Hardcoded credentials'),
        ('APPROVE', None, 'Safe parameterized query'),
    ]),
    ('Near-Perfect (correct, no severity/comment)', [
        ('REJECT', None, None),
        ('REJECT', None, None),
        ('REJECT', None, None),
        ('REJECT', None, None),
        ('APPROVE', None, None),
    ]),
    ('One Catastrophic (approved a real bug)', [
        ('APPROVE', None, None),
        ('REJECT', None, None),
        ('REJECT', None, None),
        ('REJECT', None, None),
        ('APPROVE', None, None),
    ]),
    ('Mixed (3 correct + 2 wrong)', [
        ('REJECT','HIGH','path traversal'),
        ('APPROVE', None, None),
        ('REJECT', None, None),
        ('REJECT','CRITICAL','command injection'),
        ('REJECT', None, None),
    ]),
    ('Worst Case (all approved = all catastrophic)', [
        ('APPROVE', None, None),
        ('APPROVE', None, None),
        ('APPROVE', None, None),
        ('APPROVE', None, None),
        ('APPROVE', None, None),
    ]),
]

for task_id in ['easy', 'medium', 'hard']:
    print(f'\n{"="*62}')
    print(f'  TASK: {task_id.upper()}')
    print(f'{"="*62}')
    for name, steps in scenarios:
        env = CodeReviewEnvironment(task_id=task_id)
        env.reset()
        for action, severity, comment in steps:
            env.step(action=action, severity=severity, comment=comment)
        score = env.grader_score
        step_scores = [round(s, 3) for s in env._step_scores]
        mean = round(sum(env._step_scores) / len(env._step_scores), 4)
        print(f'  Scenario : {name}')
        print(f'  Steps    : {step_scores}')
        print(f'  Mean     : {mean}   approve_bugs={env.approve_bug_count}   perfect={env.perfect_count}/{len(step_scores)}')
        print(f'  FINAL    : {score}')
        print()
