import csv
import argparse




def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--grade_csv_file", required=True)
	parser.add_argument("--output_file", required=True)

	args = parser.parse_args()
	return args


def main():
	args = getArgs()

	emails = getEmails(args.grade_csv_file)
	printEmails(args.output_file)



if __name__ == "__main__":
	main()