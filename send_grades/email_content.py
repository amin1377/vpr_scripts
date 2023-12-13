import csv
import argparse




def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--grade_csv_file", required=True)
	parser.add_argument("--output_file", required=True)

	args = parser.parse_args()
	return args

def getGradeInfo(csv_file):
	data = []

	with open(csv_file, 'r', newline='') as csv_file:
		csv_reader = csv.DictReader(csv_file)
		for row in csv_reader:
			data.append(row)

	return data

def getEmails(csv_file):
	all_grade_info = getGradeInfo(csv_file)
	# print(all_grade_info)

	data = []
	for student_grade_info in all_grade_info:
		email = f"Hello {student_grade_info['first']},\n\n" \
		"Hope everything is going well with assignment 4!\n\n" \
		"Here is the feedback for your second assignment. You will find all my comments inlined in the attached PDF " \
		"and below is the breakdown of your grade. Hope this feedback is helpful for your A4 submission.\n\n" \
		f"Correctness: {student_grade_info['correctness']} out of 3.0\n" \
		f"SIV quality: {student_grade_info['quality']} out of 8.0\n" \
		f"Table II and explanation: {student_grade_info['tableii']} out of 3.0\n" \
		f"Table III and explanation: {student_grade_info['tableiii']} out of 2.0\n" \
		f"Enhanced architecture: {student_grade_info['new_arch']} out of 3.0\n" \
		f"Coding style: {student_grade_info['code']} out of 1.0\n" \
		f"Report quality: {student_grade_info['report']} out of 2.0\n" \
		f"Bonus: {student_grade_info['bonus']} out of 1.0\n" \
		f"Total: {student_grade_info['total']} out of 22.0\n\n" \
		"Let me know if you have any questions about the grading/comments.\n\n" \
		"Thanks,\n" \
		"Amin"
		print(email)
		data.append([student_grade_info['email'], email])


def main():
	args = getArgs()

	emails = getEmails(args.grade_csv_file)
	# printEmails(args.output_file)



if __name__ == "__main__":
	main()