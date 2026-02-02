from modules.db import Problems,Problem_topics,engine
from sqlmodel import Session,select
import json

def seedToDb(problems):
    try:
        with Session(engine) as session:
            for problem in problems:
                prob = Problems(title=problem['title'],statement=problem['statement'],example=problem['example'],difficulty=problem['difficulty'],expected_time=problem['expected_time'])
                # print(problem)
                session.add(prob)
                session.commit()
                session.refresh(prob)
            print("all problem added")
    except Exception as e :
        print(e)

def seedToDbTopics(problems):
    try:
        with Session(engine) as session:
            for problem in problems:
                stmt = select(Problems).where(
                    Problems.title == problem["title"]
                )
                prob = session.exec(stmt).first()

                if not prob:
                    continue

                for topic_name in problem["topics"]:
                    topic = Problem_topics(
                        problem_id=prob.problem_id,
                        topic=topic_name
                    )
                    session.add(topic)

            session.commit()
            print("all topics added")

    except Exception as e:
        print(e)


if __name__ =='__main__':
    with open ('helpers\problems.json','r') as file:
        data = json.load(file)
        seedToDbTopics(data['problems'])