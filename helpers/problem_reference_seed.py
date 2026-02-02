from modules.db import Problems, Problem_Reference, engine
from sqlmodel import Session, select
import json


def seed_problem_references(references):
	try:
		with Session(engine) as session:
			for ref in references:
				stmt = select(Problems).where(Problems.title == ref["title"])
				prob = session.exec(stmt).first()

				if not prob:
					continue

				# existing = session.exec(
				# 	select(ProblemReference).where(
				# 		ProblemReference.problem_id == prob.problem_id
				# 	)
				# ).first()

				# if existing:
				# 	continue

				reference = Problem_Reference(
					problem_id=prob.problem_id,
					optimal_approach=ref["optimal_approach"],
					time_complexity=ref["time_complexity"],
					space_complexity=ref["space_complexity"],
					key_insights=ref["key_insights"],
					common_pitfalls=ref.get("common_pitfalls"),
					pseudocode=ref.get("pseudocode"),
				)
				session.add(reference)

			session.commit()
			print("problem references added")
	except Exception as e:
		print(e)


if __name__ == "__main__":
	with open("helpers\\problems_reference.json", "r") as file:
		data = json.load(file)
		seed_problem_references(data["references"])
